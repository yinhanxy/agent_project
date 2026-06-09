import pytest

from app.agent.graph.nodes.coordinator import coordinator_node
from app.agent.graph.nodes.knowledge import knowledge_node
from app.agent.graph.nodes.finalize import finalize_node


@pytest.mark.asyncio
async def test_coordinator_falls_back_on_llm_error(monkeypatch):
    import app.agent.graph.nodes.coordinator as co

    async def _boom(_m):
        raise RuntimeError("LLM down")

    class _Fake:
        ainvoke = staticmethod(_boom)
    monkeypatch.setattr(co, "chat_model", _Fake())

    update = await coordinator_node({"query": "随便", "history": []})
    # 降级为保守 plan，不抛异常
    assert update["plan"]["need_retrieval"] is True
    assert update["trace"][0]["status"] == "failed"


@pytest.mark.asyncio
async def test_knowledge_degrades_on_retrieval_error(monkeypatch):
    import app.agent.graph.nodes.knowledge as kn

    async def _boom(query, filter_meta=None):
        raise RuntimeError("vector store down")
    monkeypatch.setattr(kn.rag_service, "get_documents_for_agent", _boom)

    update = await knowledge_node({"query": "x", "identity": None})
    assert update["documents"] == []
    assert update["is_enough"] is False
    assert update["trace"][0]["status"] == "failed"


@pytest.mark.asyncio
async def test_finalize_returns_fallback_text_on_llm_error(monkeypatch):
    import app.agent.graph.nodes.finalize as fz

    async def _boom(_m):
        raise RuntimeError("LLM down")

    class _Fake:
        ainvoke = staticmethod(_boom)
    monkeypatch.setattr(fz, "chat_model", _Fake())

    update = await finalize_node({"query": "x", "documents": [], "history": []})
    assert update["final_answer"]            # 非空兜底文本
    assert update["trace"][0]["status"] == "failed"
