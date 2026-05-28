import json
import os
from typing import List, Optional, AsyncGenerator

import httpx
import openai
from langsmith import traceable

from app.agent.agent_middleware import (
    on_agent_start, on_agent_end,
    on_tool_call, on_tool_result,
    on_model_call, on_model_response,
)
from app.agent.agent_tools import TOOLS, TOOL_SCHEMAS, get_rag_citations, set_rag_user_id
from app.core.logger_handler import logger
from app.services import session_manager as sm
from app.utils.prompt_loader import load_prompt

# ── token 估算 ────────────────────────────────────────────────────────────────
# 流式过程中用 tiktoken 粗估 token 数（qwen 非精确，仅用于实时跳动），
# 每轮 LLM 调用结束后由 API 返回的精确 usage 校准。

_token_encoder = None


def _get_encoder():
    global _token_encoder
    if _token_encoder is None:
        try:
            import tiktoken
            _token_encoder = tiktoken.get_encoding("cl100k_base")
        except Exception as e:  # tiktoken 不可用时降级为字符估算
            logger.warning(f"[token估算] tiktoken 不可用，降级为字符估算: {e}")
            _token_encoder = False
    return _token_encoder


def _estimate_text_tokens(text: str) -> int:
    if not text:
        return 0
    enc = _get_encoder()
    if enc:
        return len(enc.encode(text))
    return max(1, len(text) // 2)  # 降级：约 2 字符/token


def _estimate_messages_tokens(messages: list) -> int:
    total = 0
    for m in messages:
        content = m.get("content")
        if isinstance(content, str):
            total += _estimate_text_tokens(content)
        for tc in m.get("tool_calls") or []:
            total += _estimate_text_tokens(tc.get("function", {}).get("arguments", ""))
        total += 4  # 每条消息的角色/分隔符开销近似
    return total


def _max_tool_rounds() -> int:
    """工具调用循环的最大轮数上限（防止模型持续请求工具导致无限循环/烧 token）。"""
    try:
        return max(1, int(os.getenv("AGENT_MAX_TOOL_ROUNDS", "8")))
    except (TypeError, ValueError):
        return 8


class AgentLoop:
    """
    自实现的 Tool Calling Agent 循环。

    设计原则：
    - 实例无状态（history/query 每次传入），全局单例安全复用
    - 使用 OpenAI SDK 访问 DashScope / Ollama 的兼容接口，获得真 token 流
    - 中间件钩子（agent_middleware.py）挂载在关键节点，不侵入主循环
    """

    def __init__(self):
        self._client: Optional[openai.AsyncOpenAI] = None
        self.system_prompt: str = load_prompt("main_prompt")
        self.tools: dict = TOOLS
        self.tool_schemas: list = TOOL_SCHEMAS

    # ── 客户端懒初始化 ────────────────────────────────────────────────────────

    @property
    def client(self) -> openai.AsyncOpenAI:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def _build_client(self) -> openai.AsyncOpenAI:
        llm_type = os.getenv("LLM_TYPE", "ALIYUN").upper()
        # 读超时是「两次 chunk 之间」的最大间隔（不是整段流的总时长），
        # 故 60s 不会截断长回答；连接超时单独设短一些；失败重试 2 次。
        timeout = httpx.Timeout(float(os.getenv("LLM_TIMEOUT", "60")), connect=10.0)
        max_retries = int(os.getenv("LLM_MAX_RETRIES", "2"))
        if llm_type == "OLLAMA":
            base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/") + "/v1"
            return openai.AsyncOpenAI(
                base_url=base_url, api_key="ollama",
                timeout=timeout, max_retries=max_retries,
            )
        return openai.AsyncOpenAI(
            base_url=os.getenv(
                "ALIYUN_BASE_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
            api_key=os.getenv("ALIYUN_ACCESS_KEY_SECRET"),
            timeout=timeout,
            max_retries=max_retries,
        )

    def _model_name(self) -> str:
        llm_type = os.getenv("LLM_TYPE", "ALIYUN").upper()
        if llm_type == "OLLAMA":
            return os.getenv("OLLAMA_MODEL_NAME", "qwen3:7b")
        return os.getenv("ALIYUN_MODEL_NAME", "qwen3-max")

    # ── 消息构建 ──────────────────────────────────────────────────────────────

    def _build_messages(self, history: list, query: str) -> list:
        messages = [{"role": "system", "content": self.system_prompt}]
        for user_msg, assistant_msg in (history or []):
            messages.append({"role": "user", "content": user_msg})
            messages.append({"role": "assistant", "content": assistant_msg})
        messages.append({"role": "user", "content": query})
        return messages

    # ── 工具执行 ──────────────────────────────────────────────────────────────

    async def _execute_tool(self, name: str, arguments: str) -> str:
        tool_fn = self.tools.get(name)
        if tool_fn is None:
            return f"工具 {name} 不存在"
        try:
            args = json.loads(arguments) if arguments.strip() else {}
            return str(await tool_fn(**args))
        except Exception as e:
            logger.error(f"[Tool] {name} 执行异常: {e}", exc_info=True)
            return f"工具执行失败: {e}"

    # ── 非流式执行 ────────────────────────────────────────────────────────────

    @traceable
    async def run(self, query: str, history: list = None) -> dict:
        """完整执行，返回 {response, steps}"""
        messages = self._build_messages(history, query)
        steps = []
        on_agent_start(messages)

        max_rounds = _max_tool_rounds()
        for round_idx in range(max_rounds + 1):
            on_model_call(messages)
            # 最后一轮禁用工具，强制模型给出文字答复，保证循环必然终止
            last_round = round_idx == max_rounds
            response = await self.client.chat.completions.create(
                model=self._model_name(),
                messages=messages,
                tools=self.tool_schemas,
                tool_choice="none" if last_round else "auto",
            )
            msg = response.choices[0].message
            on_model_response(bool(msg.tool_calls), len(msg.content or ""))

            if not msg.tool_calls:
                result = msg.content or ""
                on_agent_end(result, steps)
                return {"response": result, "steps": steps}

            # 将 assistant 消息（含 tool_calls）追加到上下文
            messages.append(msg.model_dump(exclude_unset=True))

            for tc in msg.tool_calls:
                on_tool_call(tc.function.name, tc.function.arguments)
                result = await self._execute_tool(tc.function.name, tc.function.arguments)
                on_tool_result(tc.function.name, result)

                steps.append({
                    "tool": tc.function.name,
                    "tool_input": tc.function.arguments,
                    "tool_output": result,
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

        # 兜底：达到工具调用上限仍未给出文字答复
        fallback = "（已达到工具调用次数上限，请重试或换个问法）"
        on_agent_end(fallback, steps)
        return {"response": fallback, "steps": steps}

    # ── 流式执行 ──────────────────────────────────────────────────────────────

    @traceable
    async def stream(
        self, query: str, history: list = None
    ) -> AsyncGenerator[dict, None]:
        """
        真 token 级流式执行。

        yield 事件：
          {"type": "token", "data": str}             —— LLM 输出 token
          {"type": "step",  "data": {tool, ...}}     —— 工具调用记录
          {"type": "usage", "tokens": int, ...}      —— 实时 token 估算
          {"type": "done",  "steps": list, "tokens"} —— 全部完成（精确总数）
        """
        messages = self._build_messages(history, query)
        steps = []
        on_agent_start(messages)

        committed_tokens = 0  # 已完成各轮 LLM 调用的精确 total_tokens 之和

        max_rounds = _max_tool_rounds()
        for round_idx in range(max_rounds + 1):
            on_model_call(messages)
            # 最后一轮禁用工具，强制模型输出文字答复，保证循环必然终止
            last_round = round_idx == max_rounds
            prompt_est = _estimate_messages_tokens(messages)
            # 思考期先发一个初始估算（已消耗的输入 token），让前端立刻有数字开始增长
            yield {"type": "usage", "tokens": committed_tokens + prompt_est, "estimated": True}
            stream = await self.client.chat.completions.create(
                model=self._model_name(),
                messages=messages,
                tools=self.tool_schemas,
                tool_choice="none" if last_round else "auto",
                stream=True,
                stream_options={"include_usage": True},
            )

            # 累积本轮输出
            content_buf = ""
            tool_calls_buf: dict[int, dict] = {}  # chunk index -> {id, name, args}
            turn_usage_total: Optional[int] = None
            last_emit_len = 0

            async for chunk in stream:
                # include_usage 的最后一帧 choices 为空、仅带 usage
                if getattr(chunk, "usage", None) is not None:
                    turn_usage_total = chunk.usage.total_tokens
                if not chunk.choices:
                    continue

                choice = chunk.choices[0]
                delta = choice.delta

                if delta.content:
                    content_buf += delta.content
                    yield {"type": "token", "data": delta.content}

                    # 节流：内容每增长约 20 字符发一次实时估算
                    if len(content_buf) - last_emit_len >= 20:
                        last_emit_len = len(content_buf)
                        running = committed_tokens + prompt_est + _estimate_text_tokens(content_buf)
                        yield {"type": "usage", "tokens": running, "estimated": True}

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_buf:
                            tool_calls_buf[idx] = {"id": "", "name": "", "args": ""}
                        if tc.id:
                            tool_calls_buf[idx]["id"] = tc.id
                        if tc.function and tc.function.name:
                            tool_calls_buf[idx]["name"] += tc.function.name
                        if tc.function and tc.function.arguments:
                            tool_calls_buf[idx]["args"] += tc.function.arguments

            # 本轮结束：用精确 usage 累加；拿不到则用估算兜底
            if turn_usage_total is not None:
                committed_tokens += turn_usage_total
            else:
                committed_tokens += prompt_est + _estimate_text_tokens(content_buf)

            on_model_response(bool(tool_calls_buf), len(content_buf))

            if not tool_calls_buf:
                break  # 无工具调用，流式输出已完成

            # 追加 assistant 消息（含 tool_calls 结构）
            tool_calls_list = [
                {
                    "id": v["id"],
                    "type": "function",
                    "function": {"name": v["name"], "arguments": v["args"]},
                }
                for v in tool_calls_buf.values()
            ]
            messages.append({
                "role": "assistant",
                "content": content_buf or None,
                "tool_calls": tool_calls_list,
            })

            # 顺序执行各工具
            for tc in tool_calls_buf.values():
                on_tool_call(tc["name"], tc["args"])
                result = await self._execute_tool(tc["name"], tc["args"])
                on_tool_result(tc["name"], result)

                step = {
                    "tool": tc["name"],
                    "tool_input": tc["args"],
                    "tool_output": result,
                }
                steps.append(step)
                yield {"type": "step", "data": step}

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                })

        on_agent_end("", steps)
        yield {"type": "done", "steps": steps, "tokens": committed_tokens}


# ── 全局单例（实例无状态，多请求安全复用）────────────────────────────────────
agent_loop = AgentLoop()


# ── 对外接口（与旧 agent.py 签名兼容）───────────────────────────────────────

async def get_agent_response(
    query: str,
    history: Optional[List[tuple]] = None,
    **kwargs,
) -> dict:
    """非流式调用，返回 {response: str, steps: list}"""
    return await agent_loop.run(query, history)


@traceable
async def get_agent_stream_response(
    query: str,
    session_id: str,
    user_id: str,
    **kwargs,
) -> AsyncGenerator[str, None]:
    """SSE 流式调用，yield Server-Sent Events 格式字符串"""
    history = await sm.session_manager.get_history(session_id, user_id)
    set_rag_user_id(user_id)
    logger.info(f"[Agent流式] 开始 user={user_id} session={session_id}")

    # 初始帧：告知客户端 session_id
    yield f"data: {json.dumps({'type': 'response', 'content': '', 'session_id': session_id}, ensure_ascii=False)}\n\n"

    full_response: list[str] = []
    steps: list = []
    total_tokens = 0

    async for event in agent_loop.stream(query, history):
        if event["type"] == "token":
            full_response.append(event["data"])
            yield f"data: {json.dumps({'type': 'response', 'content': event['data']}, ensure_ascii=False)}\n\n"
        elif event["type"] == "usage":
            yield f"data: {json.dumps({'type': 'usage', 'tokens': event['tokens'], 'estimated': True}, ensure_ascii=False)}\n\n"
        elif event["type"] == "step":
            steps.append(event["data"])
        elif event["type"] == "done":
            steps = event["steps"]
            total_tokens = event.get("tokens", 0)

    response = "".join(full_response) or "抱歉，我无法理解您的请求。"
    await sm.session_manager.add_message(session_id, user_id, query, response)

    citations = get_rag_citations()
    yield f"data: {json.dumps({'type': 'done', 'session_id': session_id, 'citations': citations, 'tokens': total_tokens}, ensure_ascii=False)}\n\n"
    logger.info(f"[Agent流式] 完成 session={session_id} steps={len(steps)} citations={len(citations)} tokens={total_tokens}")
