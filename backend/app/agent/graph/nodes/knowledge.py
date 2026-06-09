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
    """检索知识依据。权限 identity 从 state 取，绝不走隐式传递。"""
    writer = safe_get_stream_writer()
    writer({"kind": "step", "id": "tool_rag_summary_tools", "status": "running",
            "level": "info", "detail": "正在检索相关知识库", "title": "检索相关知识库"})

    identity = state.get("identity")
    node_status = "done"
    try:
        filter_meta = await _build_filter(identity)
        result = await rag_service.get_documents_for_agent(state["query"], filter_meta=filter_meta)
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

    writer({"kind": "step", "id": "tool_rag_summary_tools", "status": "done",
            "level": "success", "detail": f"已检索 {len(citations)} 个文档",
            "title": "已检索知识库"})

    return {
        "documents": documents,
        "citations": citations,
        "is_enough": is_enough,
        "trace": [{"agent": "knowledge", "status": node_status,
                   "output": f"documents={len(documents)} is_enough={is_enough} max_score={max_score}"}],
    }
