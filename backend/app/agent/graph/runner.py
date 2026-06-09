from typing import AsyncGenerator, Optional

from app.agent.graph.build import build_graph
from app.agent.graph.stream_bridge import translate_stream_item
from app.agent.token_utils import (
    estimate_history_query_tokens,
    estimate_text_tokens,
)
from app.utils.auth_utils import RequestIdentity


def _initial_plan() -> list:
    return [
        {"id": "task_understood", "title": "识别任务类型", "status": "todo", "level": "muted"},
        {"id": "answer_generated", "title": "生成最终回答", "status": "todo", "level": "muted"},
    ]


def _chunk_total_tokens(message_chunk) -> Optional[int]:
    """从 LangChain 的 message chunk 上抠 total_tokens（如果可用）。

    不同 provider/版本暴露字段不一致，按优先级尝试：
      1. usage_metadata.total_tokens（LangChain 标准接口）
      2. response_metadata.token_usage.total_tokens（OpenAI 风格）
    都拿不到返回 None，由调用方走估算兜底。
    """
    if message_chunk is None:
        return None
    usage = getattr(message_chunk, "usage_metadata", None)
    if isinstance(usage, dict):
        total = usage.get("total_tokens")
        if total:
            return int(total)
    rmeta = getattr(message_chunk, "response_metadata", None)
    if isinstance(rmeta, dict):
        token_usage = rmeta.get("token_usage") or rmeta.get("usage")
        if isinstance(token_usage, dict):
            total = token_usage.get("total_tokens")
            if total:
                return int(total)
    return None


class GraphRunner:
    """LangGraph 编排入口。stream() 产出与 AgentLoop.stream() 相同 schema 的事件。"""

    def __init__(self):
        self._graph = build_graph()

    async def stream(
        self, query: str, history: list = None, identity: Optional[RequestIdentity] = None
    ) -> AsyncGenerator[dict, None]:
        yield {"type": "agent_plan", "data": _initial_plan()}

        state = {
            "query": query,
            "history": history or [],
            "identity": identity,
            "plan": {},
            "documents": [],
            "citations": [],
            "trace": [],
        }

        # ── token 计数 ────────────────────────────────────────────────────────
        # 思考期：先用 (history + query) 给前端一个起跳数字，避免长时间显示 0。
        prompt_est = estimate_history_query_tokens(history or [], query or "")
        running_tokens = prompt_est            # 当前累计（估算口径）
        accurate_tokens: Optional[int] = None  # provider 给出的精确 total（若可用）
        content_buf = ""                       # finalize 节点已输出文字
        last_usage_emit_len = 0                # 节流：上次发 usage 时的 content_buf 长度

        yield {"type": "usage", "tokens": running_tokens, "estimated": True}

        full_answer: list[str] = []
        final_citations: list = []
        async for item in self._graph.astream(
            state, stream_mode=["messages", "custom", "values"]
        ):
            mode, payload = item
            if mode == "values":
                if isinstance(payload, dict) and payload.get("citations") is not None:
                    final_citations = payload["citations"]
                continue

            # 在 messages 模式下尽量从 chunk 读精确 usage（最后一帧通常带）
            if mode == "messages" and isinstance(payload, tuple) and len(payload) == 2:
                message_chunk, _meta = payload
                total = _chunk_total_tokens(message_chunk)
                if total is not None:
                    accurate_tokens = total

            for event in translate_stream_item(item):
                if event["type"] == "token":
                    delta = event["data"]
                    full_answer.append(delta)
                    content_buf += delta
                    # 节流：finalize 输出每多约 20 字符发一次 usage 估算
                    if len(content_buf) - last_usage_emit_len >= 20:
                        last_usage_emit_len = len(content_buf)
                        running_tokens = prompt_est + estimate_text_tokens(content_buf)
                        yield {
                            "type": "usage",
                            "tokens": accurate_tokens or running_tokens,
                            "estimated": accurate_tokens is None,
                        }
                yield event

        yield {
            "type": "agent_step_update",
            "data": {"id": "answer_generated", "status": "done",
                     "level": "success", "detail": "已生成最终回答", "title": "生成最终回答"},
        }
        # done 帧用精确值优先，否则回落估算
        final_tokens = accurate_tokens if accurate_tokens is not None else (
            prompt_est + estimate_text_tokens(content_buf)
        )
        yield {"type": "done", "steps": [], "tokens": final_tokens, "citations": final_citations}


# 全局单例（图编译一次复用）
graph_runner = GraphRunner()
