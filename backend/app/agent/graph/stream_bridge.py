"""把 LangGraph astream 的输出翻译成与 AgentLoop.stream() 相同 schema 的事件字典。

事件 schema（对齐 app/agent/agent.py 的内部事件）：
  {"type": "token", "data": str}
  {"type": "agent_step_update", "data": {...}}
"""
from typing import Iterator

# 只放行该节点产生的 LLM token 给用户；其余节点（knowledge 内的 HyDE 等）token 丢弃
_USER_FACING_LLM_NODE = "finalize"

# custom 事件里允许翻译成 step_update 的字段
_STEP_FIELDS = ("id", "status", "level", "detail", "title")


def translate_stream_item(item) -> Iterator[dict]:
    """翻译单个 astream 产出项。返回 0..N 个内部事件字典。"""
    # 多 stream_mode 标准形态：(mode, payload) 元组
    mode, payload = item

    if mode == "messages":
        message_chunk, metadata = payload
        if metadata.get("langgraph_node") != _USER_FACING_LLM_NODE:
            return
        content = getattr(message_chunk, "content", "") or ""
        if content:
            yield {"type": "token", "data": content}
        return

    if mode == "custom":
        if not isinstance(payload, dict) or payload.get("kind") != "step":
            return
        data = {k: payload[k] for k in _STEP_FIELDS if k in payload}
        yield {"type": "agent_step_update", "data": data}
        return
