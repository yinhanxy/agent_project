from typing import AsyncGenerator, Optional

from app.agent.graph.build import build_graph
from app.agent.graph.stream_bridge import translate_stream_item
from app.agent.token_utils import (
    estimate_history_query_tokens,
    estimate_text_tokens,
    extract_total_tokens,
)
from app.utils.auth_utils import RequestIdentity


def _initial_plan() -> list:
    return [
        {"id": "task_understood", "title": "识别任务类型", "status": "todo", "level": "muted"},
        {"id": "answer_generated", "title": "生成最终回答", "status": "todo", "level": "muted"},
    ]


def _chunk_total_tokens(message_chunk) -> Optional[int]:
    """从 LangChain message chunk 上抠 total_tokens；委托 token_utils.extract_total_tokens（公共实现）。"""
    return extract_total_tokens(message_chunk)


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
        final_answer_state = ""
        graph_token_usage = 0
        async for item in self._graph.astream(
            state, stream_mode=["messages", "custom", "values"]
        ):
            mode, payload = item
            if mode == "values":
                if isinstance(payload, dict):
                    if payload.get("citations") is not None:
                        final_citations = payload["citations"]
                    if payload.get("final_answer"):
                        final_answer_state = payload["final_answer"]
                    if payload.get("token_usage") is not None:
                        graph_token_usage = payload["token_usage"]
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

        # 兜底：若全程没有任何 token 流出（如 finalize 异常或 provider 没流 token），
        # 用最终 state 的 final_answer 补一帧，保证用户能看到内容。
        if not full_answer and final_answer_state:
            yield {"type": "token", "data": final_answer_state}
            content_buf = final_answer_state

        yield {
            "type": "agent_step_update",
            "data": {"id": "answer_generated", "status": "done",
                     "level": "success", "detail": "已生成最终回答", "title": "生成最终回答"},
        }
        # done 帧 token 口径：优先用图内各节点累计的精确 total（含 coordinator/gap/finalize）；
        # 为 0 时回落到 accurate_tokens（finalize chunk 精确值）或 prompt+finalize 输出的估算
        estimated_total = prompt_est + estimate_text_tokens(content_buf)
        final_tokens = graph_token_usage if graph_token_usage else (
            accurate_tokens if accurate_tokens is not None else estimated_total
        )
        yield {"type": "done", "steps": [], "tokens": final_tokens, "citations": final_citations}


# 全局单例（图编译一次复用）
graph_runner = GraphRunner()
