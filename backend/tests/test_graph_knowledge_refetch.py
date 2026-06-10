import pytest

from app.agent.graph.nodes.knowledge import knowledge_node


@pytest.mark.asyncio
async def test_knowledge_uses_reformulated_query_on_retry(monkeypatch):
    captured = {}
    import app.agent.graph.nodes.knowledge as kn

    async def _fake_get(query, filter_meta=None):
        captured["query"] = query
        return {"documents": ["doc"], "citations": [{"filename": "a"}],
                "is_enough": True, "max_score": 0.9}

    monkeypatch.setattr(kn.rag_service, "get_documents_for_agent", _fake_get)

    update = await knowledge_node({"query": "那它呢", "identity": None,
                                   "reformulated_query": "2025版差旅报销上限"})
    assert captured["query"] == "2025版差旅报销上限"     # 重检索用改写后的 query
    assert update["max_score"] == 0.9                     # 暴露 max_score 供 critic
    assert update["is_enough"] is True
    assert update["trace"][0]["agent"] == "knowledge_retry"


@pytest.mark.asyncio
async def test_knowledge_first_pass_uses_original_query(monkeypatch):
    captured = {}
    import app.agent.graph.nodes.knowledge as kn

    async def _fake_get(query, filter_meta=None):
        captured["query"] = query
        return {"documents": [], "citations": [], "is_enough": False, "max_score": 0.1}

    monkeypatch.setattr(kn.rag_service, "get_documents_for_agent", _fake_get)

    update = await knowledge_node({"query": "原始问题", "identity": None})
    assert captured["query"] == "原始问题"               # 首检索用原 query
    assert update["max_score"] == 0.1
    assert update["trace"][0]["agent"] == "knowledge"     # 首检索 trace 名不变
