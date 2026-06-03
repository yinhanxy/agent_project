import pytest

from app.agent.graph.nodes.knowledge import knowledge_node
from app.utils.auth_utils import RequestIdentity


@pytest.mark.asyncio
async def test_identity_drives_permission_filter(monkeypatch):
    """非管理员用户的 user_id/dept_id 必须传进 build_accessible_filter。"""
    seen = {}

    async def _fake_filter(user_id, is_admin=False, dept_id=None):
        seen.update(user_id=user_id, is_admin=is_admin, dept_id=dept_id)
        return {"scoped": True}

    async def _fake_get_docs(query, filter_meta=None):
        seen["filter_meta"] = filter_meta
        return {"documents": ["x"], "citations": [], "summary": "", "error": None}

    import app.agent.graph.nodes.knowledge as kn
    monkeypatch.setattr(kn.kb_service, "build_accessible_filter", _fake_filter)
    monkeypatch.setattr(kn.rag_service, "get_documents_for_agent", _fake_get_docs)

    identity = RequestIdentity(user_id="u9", is_admin=False, dept_id="d3")
    await knowledge_node({"query": "q", "identity": identity})

    assert seen["user_id"] == "u9"
    assert seen["is_admin"] is False
    assert seen["dept_id"] == "d3"
    assert seen["filter_meta"] == {"scoped": True}


@pytest.mark.asyncio
async def test_missing_identity_yields_no_filter(monkeypatch):
    """无 identity 时 filter_meta 为 None（与现有 agent_tools 行为一致）。"""
    seen = {}

    async def _fake_get_docs(query, filter_meta=None):
        seen["filter_meta"] = filter_meta
        return {"documents": [], "citations": [], "summary": "", "error": None}

    import app.agent.graph.nodes.knowledge as kn
    monkeypatch.setattr(kn.rag_service, "get_documents_for_agent", _fake_get_docs)

    await knowledge_node({"query": "q", "identity": None})
    assert seen["filter_meta"] is None
