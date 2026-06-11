from typing import Optional

from app.agent.graph._stream import safe_get_stream_writer
from app.agent.graph.state import AgentState
from app.rag.rag_service import rag_service
from app.services.kb_service import kb_service
from app.utils.auth_utils import RequestIdentity


async def _build_filter(identity: Optional[RequestIdentity]):
    if not identity or not identity.user_id:
        return None
    return await kb_service.build_accessible_filter(
        identity.user_id, is_admin=identity.is_admin, dept_id=identity.dept_id
    )


async def knowledge_node(state: AgentState) -> dict:
    """检索知识依据。权限 identity 从 state 取，绝不走隐式传递。

    若 state 带 reformulated_query（critic 改写救援），用它重检索；否则用原 query。
    """
    writer = safe_get_stream_writer()
    reformulated = state.get("reformulated_query")
    actual_query = reformulated or state["query"]
    is_retry = bool(reformulated)

    if is_retry:
        preview = actual_query[:30] + ("..." if len(actual_query) > 30 else "")
        writer({"kind": "step", "id": "knowledge_refetching", "status": "running",
                "level": "info", "detail": f"改写后的查询：{preview}",
                "title": "用更精细的查询重新检索"})
    else:
        writer({"kind": "step", "id": "tool_rag_summary_tools", "status": "running",
                "level": "info", "detail": "正在检索相关知识库", "title": "检索相关知识库"})

    identity = state.get("identity")
    node_status = "done"
    try:
        filter_meta = await _build_filter(identity)
        result = await rag_service.get_documents_for_agent(actual_query, filter_meta=filter_meta)
        documents = result.get("documents", [])
        citations = result.get("citations", [])
        # is_enough 由 rag_service 按缺口阈值（相关度）判定；缺字段时回退为"有无文档"，兼容旧返回/桩
        is_enough = result.get("is_enough", bool(documents))
        max_score = result.get("max_score")
    except Exception as e:
        from app.core.logger_handler import logger
        logger.error(f"[Knowledge] 检索失败，降级为空依据: {e}", exc_info=True)
        documents, citations, is_enough, max_score = [], [], False, None
        node_status = "failed"

    writer({"kind": "step",
            "id": "knowledge_refetching" if is_retry else "tool_rag_summary_tools",
            "status": "done", "level": "success",
            "detail": f"已检索 {len(citations)} 个文档", "title": "已检索知识库"})

    agent_name = "knowledge_retry" if is_retry else "knowledge"
    return {
        "documents": documents,
        "citations": citations,
        "is_enough": is_enough,
        "max_score": max_score,
        "trace": [{"agent": agent_name, "status": node_status,
                   "output": f"actual_query={actual_query} documents={len(documents)} "
                             f"is_enough={is_enough} max_score={max_score}"}],
    }
