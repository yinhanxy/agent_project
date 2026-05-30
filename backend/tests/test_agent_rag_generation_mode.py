import pytest

from app.agent import agent_tools
from app.utils.auth_utils import RequestIdentity


async def _filter_for_user(identity):
    return {"user_id": {"$eq": identity.user_id}}


async def _no_filter(user_id):
    return None


class _FakeRagService:
    def __init__(self):
        self.agent_calls = []
        self.rag_calls = []

    async def get_documents_for_agent(self, query, filter_meta=None):
        self.agent_calls.append((query, filter_meta))
        return {
            "documents": ["Python 是动态语言。", "Java 运行在 JVM 上。"],
            "citations": [
                {
                    "filename": "languages.md",
                    "chunk_preview": "Python 是动态语言。",
                    "score": 0.91,
                    "kb_id": "kb-1",
                }
            ],
            "error": None,
        }

    async def get_documents_and_summary(self, query, filter_meta=None):
        self.rag_calls.append((query, filter_meta))
        return {
            "summary": "这是 RAG 内部生成的答案。",
            "citations": [
                {
                    "filename": "summary.md",
                    "chunk_preview": "摘要来源",
                    "score": 0.82,
                    "kb_id": None,
                }
            ],
            "error": None,
        }


@pytest.mark.asyncio
async def test_agent_generation_mode_returns_context_and_structured_citations(monkeypatch):
    fake = _FakeRagService()
    monkeypatch.setenv("RAG_GENERATION_MODE", "agent")
    monkeypatch.setattr(agent_tools, "rag_service", fake)
    monkeypatch.setattr(
        agent_tools,
        "_build_rag_filter",
        _filter_for_user,
    )

    result = await agent_tools.rag_summary_tools(
        "语言区别",
        identity=RequestIdentity(user_id="u1"),
    )

    assert fake.agent_calls == [("语言区别", {"user_id": {"$eq": "u1"}})]
    assert fake.rag_calls == []
    assert "检索到的文档片段" in result
    assert "Python 是动态语言。" in result
    assert "Java 运行在 JVM 上。" in result
    assert "摘要:" not in result
    assert "[指令]" not in result
    assert "参考文档：" not in result
    assert agent_tools.get_rag_citations() == [
        {
            "filename": "languages.md",
            "chunk_preview": "Python 是动态语言。",
            "score": 0.91,
            "kb_id": "kb-1",
        }
    ]


@pytest.mark.asyncio
async def test_rag_generation_mode_keeps_legacy_summary(monkeypatch):
    fake = _FakeRagService()
    monkeypatch.setenv("RAG_GENERATION_MODE", "rag")
    monkeypatch.setattr(agent_tools, "rag_service", fake)
    monkeypatch.setattr(agent_tools, "_build_rag_filter", _no_filter)

    result = await agent_tools.rag_summary_tools("语言区别", identity=None)

    assert fake.agent_calls == []
    assert fake.rag_calls == [("语言区别", None)]
    assert "摘要: 这是 RAG 内部生成的答案。" in result
    assert agent_tools.get_rag_citations() == [
        {
            "filename": "summary.md",
            "chunk_preview": "摘要来源",
            "score": 0.82,
            "kb_id": None,
        }
    ]
