from app.agent.graph._stream import safe_get_stream_writer
from app.agent.graph.state import AgentState
from app.utils.factory import chat_model
from app.utils.prompt_loader import load_prompt

_SYSTEM_PROMPT = load_prompt("main_prompt")


def _build_messages(state: AgentState) -> list:
    documents = state.get("documents") or []
    if documents:
        context = "\n\n".join(f"【文档片段{i}】\n{d}" for i, d in enumerate(documents, 1))
        user = (
            f"请只基于以下检索到的文档片段回答用户问题；"
            f"若片段不足以回答，请明确说明知识库信息不足。\n\n"
            f"{context}\n\n用户问题：{state['query']}"
        )
    else:
        user = state["query"]
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


async def finalize_node(state: AgentState) -> dict:
    """生成最终回答。token 由 LangGraph messages 模式自动流出（节点名 finalize）。"""
    writer = safe_get_stream_writer()
    writer({"kind": "step", "id": "answer_generated", "status": "running",
            "level": "info", "detail": "正在生成最终回答", "title": "生成最终回答"})

    messages = _build_messages(state)
    msg = await chat_model.ainvoke(messages)
    answer = msg.content if hasattr(msg, "content") else str(msg)

    return {
        "final_answer": answer,
        "trace": [{"agent": "finalize", "status": "done", "output": answer[:200]}],
    }
