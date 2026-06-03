import pytest

from app.agent.graph.nodes.knowledge import knowledge_node
from app.utils.auth_utils import RequestIdentity


@pytest.mark.asyncio
async def test_knowledge_node_populates_documents_and_citations(monkeypatch):
    captured = {}

    async def _fake_get_docs(query, filter_meta=None):
        captured["filter_meta"] = filter_meta
        return {
            "documents": ["年假每年 5 天"],
            "citations": [{"filename": "制度.pdf", "score": 0.9}],
            "summary": "",
            "error": None,
        }

    async def _fake_filter(user_id, is_admin=False, dept_id=None):
        return {"user_id": user_id}

    import app.agent.graph.nodes.knowledge as kn
    monkeypatch.setattr(kn.rag_service, "get_documents_for_agent", _fake_get_docs)
    monkeypatch.setattr(kn.kb_service, "build_accessible_filter", _fake_filter)

    state = {"query": "年假几天", "identity": RequestIdentity(user_id="u1")}
    update = await knowledge_node(state)

    assert update["documents"] == ["年假每年 5 天"]
    assert update["citations"][0]["filename"] == "制度.pdf"
    assert update["is_enough"] is True
    assert captured["filter_meta"] == {"user_id": "u1"}


@pytest.mark.asyncio
async def test_knowledge_node_marks_not_enough_when_no_docs(monkeypatch):
    async def _fake_get_docs(query, filter_meta=None):
        return {"documents": [], "citations": [], "summary": "未找到", "error": None}

    async def _fake_filter(user_id, is_admin=False, dept_id=None):
        return None

    import app.agent.graph.nodes.knowledge as kn
    monkeypatch.setattr(kn.rag_service, "get_documents_for_agent", _fake_get_docs)
    monkeypatch.setattr(kn.kb_service, "build_accessible_filter", _fake_filter)

    state = {"query": "未知问题", "identity": RequestIdentity(user_id="u1")}
    update = await knowledge_node(state)

    assert update["documents"] == []
    assert update["is_enough"] is False
