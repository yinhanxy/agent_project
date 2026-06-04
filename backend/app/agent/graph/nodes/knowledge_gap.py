import json
import re

from app.agent.graph._stream import safe_get_stream_writer
from app.agent.graph.state import AgentState
from app.services.knowledge_gap_service import knowledge_gap_service
from app.core.logger_handler import logger
from app.utils.factory import chat_model

_GAP_PROMPT = """用户的问题在企业知识库中找不到明确依据。请基于这个问题，生成一条"待补充知识条目"，
只输出一个 JSON 对象，不要额外解释，格式：
{"title": "<简短标题>", "category": "<问题类型，如 财务报销/远程办公/人事>", "suggested_content": "<建议补充的内容，列出若干要点>"}"""


def _fallback_gap(fallback_question: str) -> dict:
    title = fallback_question[:50] if fallback_question else "未命名缺口"
    return {
        "title": title,
        "category": "unknown",
        "suggested_content": "建议补充该问题相关的制度依据与处理流程。",
    }


def _parse_gap(text: str, fallback_question: str) -> dict:
    if not text:
        return _fallback_gap(fallback_question)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return _fallback_gap(fallback_question)
    try:
        data = json.loads(match.group(0))
    except (json.JSONDecodeError, ValueError):
        return _fallback_gap(fallback_question)
    fb = _fallback_gap(fallback_question)
    return {
        "title": str(data.get("title") or fb["title"]),
        "category": str(data.get("category") or "unknown"),
        "suggested_content": str(data.get("suggested_content") or fb["suggested_content"]),
    }


def _build_notice_messages(query: str, gap: dict) -> list:
    system = (
        "你要如实告知用户：知识库中没有找到该问题的明确依据，系统已生成一条待补充知识条目。"
        "用简洁中文复述：缺口标题、问题类型、建议补充的内容要点。不要编造制度内容。"
    )
    user = (
        f"用户问题：{query}\n"
        f"缺口标题：{gap['title']}\n问题类型：{gap['category']}\n"
        f"建议补充内容：{gap['suggested_content']}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


async def knowledge_gap_node(state: AgentState) -> dict:
    """检索不足/缺口类问题：生成结构化缺口 → 落库（去重）→ 经 finalize 流式告知用户。"""
    query = state["query"]
    writer = safe_get_stream_writer()
    writer({"kind": "step", "id": "task_execute", "status": "running",
            "level": "info", "detail": "正在记录知识缺口", "title": "记录知识缺口"})

    msg = await chat_model.ainvoke(
        [{"role": "system", "content": _GAP_PROMPT},
         {"role": "user", "content": query}]
    )
    text = msg.content if hasattr(msg, "content") else str(msg)
    gap = _parse_gap(text, fallback_question=query)

    identity = state.get("identity")
    user_id = (identity.user_id if identity else "") or ""
    dept_id = identity.dept_id if identity else None
    save_status = "done"
    try:
        await knowledge_gap_service.save_gap(
            user_id=user_id, dept_id=dept_id, title=gap["title"],
            question=query, category=gap["category"],
            suggested_content=gap["suggested_content"],
        )
    except Exception as e:
        save_status = "failed"
        logger.error(f"[KnowledgeGap] 落库失败: {e}", exc_info=True)

    writer({"kind": "step", "id": "task_execute", "status": "done",
            "level": "success", "detail": "已记录知识缺口", "title": "记录知识缺口"})

    return {
        "task_messages": _build_notice_messages(query, gap),
        "trace": [{"agent": "knowledge_gap", "status": save_status,
                   "output": f"title={gap['title']} category={gap['category']}"}],
    }
