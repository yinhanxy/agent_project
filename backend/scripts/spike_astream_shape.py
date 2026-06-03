"""一次性探测脚本：打印 LangGraph astream 在多 stream_mode 下的真实返回形态。

运行： uv run python scripts/spike_astream_shape.py
目的： 确认 (a) 多模式下每次迭代产出的结构；(b) messages 模式里 metadata 含哪些键
      （尤其 langgraph_node，用于在 bridge 中过滤只放行 finalize 的 token）。
"""
import asyncio
from typing import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.config import get_stream_writer

from app.utils.factory import chat_model


class _State(TypedDict):
    query: str
    answer: str


async def _finalize(state: _State):
    writer = get_stream_writer()
    writer({"kind": "step", "phase": "finalize_start"})
    # 真实走一次流式 LLM，确认 messages 模式能捕获其 token
    msg = await chat_model.ainvoke(f"用一句话回答：{state['query']}")
    return {"answer": msg.content}


def _build():
    g = StateGraph(_State)
    g.add_node("finalize", _finalize)
    g.add_edge(START, "finalize")
    g.add_edge("finalize", END)
    return g.compile()


async def main():
    graph = _build()
    print("=== 开始探测 astream(stream_mode=['messages','custom']) ===")
    async for item in graph.astream(
        {"query": "你好"},
        stream_mode=["messages", "custom"],
    ):
        print("REPR:", repr(item)[:300])
        print("TYPE:", type(item))
        print("-" * 40)


if __name__ == "__main__":
    asyncio.run(main())
