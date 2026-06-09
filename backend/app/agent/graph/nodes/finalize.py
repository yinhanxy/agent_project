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

    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
    for pair in state.get("history") or []:
        if isinstance(pair, (list, tuple)) and len(pair) == 2:
            u, a = pair
            messages.append({"role": "user", "content": u or ""})
            messages.append({"role": "assistant", "content": a or ""})
    messages.append({"role": "user", "content": user})
    return messages


async def finalize_node(state: AgentState) -> dict:
    """生成最终回答。token 由 LangGraph messages 模式自动流出（节点名 finalize）。"""
    writer = safe_get_stream_writer()
    writer({"kind": "step", "id": "answer_generated", "status": "running",
            "level": "info", "detail": "正在生成最终回答", "title": "生成最终回答"})

    messages = state.get("task_messages") or _build_messages(state)
    try:
        msg = await chat_model.ainvoke(messages)
        answer = msg.content if hasattr(msg, "content") else str(msg)
        status = "done"
        from app.agent.token_utils import extract_total_tokens
        fin_tokens = extract_total_tokens(msg) or 0   # 0 表示由 runner 的流式估算口径兜底
    except Exception as e:
        from app.core.logger_handler import logger
        logger.error(f"[Finalize] 生成失败，输出兜底文本: {e}", exc_info=True)
        answer = "抱歉，生成回答时服务出现异常，请稍后重试。"
        status = "failed"
        fin_tokens = 0

    return {
        "final_answer": answer,
        "token_usage": fin_tokens,
        "trace": [{"agent": "finalize", "status": status, "output": answer[:200]}],
    }
