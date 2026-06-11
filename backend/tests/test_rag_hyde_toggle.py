import pytest
from app.rag import rag_service as rs_mod
from app.rag.rag_service import rag_service, _hyde_enabled


def test_hyde_enabled_default_true(monkeypatch):
    monkeypatch.delenv("RAG_HYDE_ENABLE", raising=False)
    assert _hyde_enabled() is True


@pytest.mark.parametrize("val", ["false", "0", "no", "FALSE"])
def test_hyde_disabled_values(monkeypatch, val):
    monkeypatch.setenv("RAG_HYDE_ENABLE", val)
    assert _hyde_enabled() is False


@pytest.mark.asyncio
async def test_retrieve_document_skips_hyde_when_disabled(monkeypatch):
    monkeypatch.setenv("RAG_HYDE_ENABLE", "false")

    # 假检索器：ainvoke 返回空子块，避免触达真实向量库
    class _FakeRetriever:
        async def ainvoke(self, q):
            _FakeRetriever.last_query = q
            return []
    fake = _FakeRetriever()
    monkeypatch.setattr(rag_service, "retriever", fake)

    # 监视 HyDE 是否被调用
    called = {"n": 0}
    async def _spy(query):
        called["n"] += 1
        return "HYPO:" + query
    monkeypatch.setattr(rag_service, "generate_hypothetical_document", _spy)

    docs = await rag_service.retrieve_document("一线城市住宿上限")
    assert called["n"] == 0                      # 关 HyDE → 不生成假设文档
    assert fake.last_query == "一线城市住宿上限"  # 直接用原 query 检索
    assert docs == []


@pytest.mark.asyncio
async def test_retrieve_document_uses_hyde_when_enabled(monkeypatch):
    monkeypatch.setenv("RAG_HYDE_ENABLE", "true")

    class _FakeRetriever:
        async def ainvoke(self, q):
            _FakeRetriever.last_query = q
            return []
    fake = _FakeRetriever()
    monkeypatch.setattr(rag_service, "retriever", fake)

    async def _spy(query):
        return "HYPO:" + query
    monkeypatch.setattr(rag_service, "generate_hypothetical_document", _spy)

    await rag_service.retrieve_document("一线城市住宿上限")
    assert fake.last_query == "HYPO:一线城市住宿上限"   # 用假设文档检索
