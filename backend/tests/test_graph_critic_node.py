import pytest

from app.agent.graph.nodes.critic import CriticVerdict, critic_node, _verdict_to_dict


class _FakeMsg:
    usage_metadata = {"total_tokens": 55}


class _FakeStructuredModel:
    def __init__(self, result, captured):
        self.result = result
        self.captured = captured

    async def ainvoke(self, messages):
        self.captured["messages"] = messages
        return {"raw": _FakeMsg(), "parsed": self.result, "parsing_error": None}


class _FakeChatModel:
    def __init__(self, result, captured):
        self.result = result
        self.captured = captured

    def with_structured_output(self, schema, include_raw=False):
        self.captured["schema"] = schema
        self.captured["include_raw"] = include_raw
        return _FakeStructuredModel(self.result, self.captured)


def test_verdict_to_dict_normalizes_illegal_verdict():
    d = _verdict_to_dict({"verdict": "???", "reason": "x"})
    assert d["verdict"] == "relevant"


@pytest.mark.asyncio
async def test_critic_relevant_has_no_reformulation(monkeypatch):
    captured = {}
    result = CriticVerdict(verdict="relevant", reason="阈值过严", reformulated_query=None)

    import app.agent.graph.nodes.critic as cr
    monkeypatch.setattr(cr, "chat_model", _FakeChatModel(result, captured))

    update = await critic_node({"query": "年假几天", "documents": ["年假为5天"], "max_score": 0.3})
    assert update["critic_verdict"]["verdict"] == "relevant"
    assert "reformulated_query" not in update      # relevant 不带改写
    assert "revision_count" not in update           # relevant 不计 revision
    assert update["token_usage"] == 55
    assert update["trace"][0]["agent"] == "critic_evidence"
    assert update["trace"][0]["status"] == "done"


@pytest.mark.asyncio
async def test_critic_needs_rewrite_returns_reformulation(monkeypatch):
    captured = {}
    result = CriticVerdict(verdict="needs_rewrite", reason="指代未消解",
                           reformulated_query="2025版差旅报销上限")

    import app.agent.graph.nodes.critic as cr
    monkeypatch.setattr(cr, "chat_model", _FakeChatModel(result, captured))

    update = await critic_node({"query": "那它呢", "documents": [], "max_score": 0.1})
    assert update["critic_verdict"]["verdict"] == "needs_rewrite"
    assert update["reformulated_query"] == "2025版差旅报销上限"
    assert update["revision_count"] == 1            # 触发一次改写计数
    assert captured["schema"] is CriticVerdict
    assert captured["include_raw"] is True


@pytest.mark.asyncio
async def test_critic_degrades_to_relevant_on_llm_error(monkeypatch):
    import app.agent.graph.nodes.critic as cr

    class _Boom:
        def with_structured_output(self, *a, **k):
            class _S:
                async def ainvoke(self, _m):
                    raise RuntimeError("LLM down")
            return _S()

    monkeypatch.setattr(cr, "chat_model", _Boom())
    update = await critic_node({"query": "x", "documents": [], "max_score": None})
    assert update["critic_verdict"]["verdict"] == "relevant"   # 降级放行，不阻塞主路径
    assert update["trace"][0]["status"] == "failed"
    assert update["token_usage"] == 0


@pytest.mark.asyncio
async def test_critic_degrades_on_parsing_error(monkeypatch):
    import app.agent.graph.nodes.critic as cr

    class _StructParseErr:
        async def ainvoke(self, messages):
            return {"raw": None, "parsed": None, "parsing_error": ValueError("bad json")}

    class _Model:
        def with_structured_output(self, schema, include_raw=False):
            return _StructParseErr()

    monkeypatch.setattr(cr, "chat_model", _Model())
    update = await critic_node({"query": "x", "documents": [], "max_score": None})
    assert update["critic_verdict"]["verdict"] == "relevant"
    assert update["trace"][0]["status"] == "failed"
