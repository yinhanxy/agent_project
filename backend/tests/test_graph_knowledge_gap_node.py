import pytest

from app.agent.graph.nodes.knowledge_gap import (
    KnowledgeGapDraft,
    knowledge_gap_node,
    _gap_to_dict,
)
from app.utils.auth_utils import RequestIdentity


def test_gap_to_dict_accepts_structured_output():
    gap = _gap_to_dict(
        KnowledgeGapDraft(
            title="设备报销",
            category="财务",
            suggested_content="1.哪些可报",
        ),
        fallback_question="远程设备损坏报销",
    )
    assert gap["title"] == "设备报销"
    assert gap["category"] == "财务"
    assert gap["suggested_content"] == "1.哪些可报"


def test_gap_to_dict_fills_empty_fields():
    gap = _gap_to_dict(
        KnowledgeGapDraft(title="", category="", suggested_content=""),
        fallback_question="远程设备损坏报销",
    )
    assert gap["title"] == "远程设备损坏报销"
    assert gap["category"] == "unknown"
    assert gap["suggested_content"]


class _FakeMsg:
    usage_metadata = {"total_tokens": 77}


class _FakeStructuredModel:
    def __init__(self, result, captured):
        self.result = result
        self.captured = captured

    async def ainvoke(self, messages):
        self.captured["messages"] = messages
        return {"raw": _FakeMsg(), "parsed": self.result, "parsing_error": None}


class _FakeModel:
    def __init__(self, result, captured):
        self.result = result
        self.captured = captured

    def with_structured_output(self, schema, include_raw=False):
        self.captured["schema"] = schema
        self.captured["include_raw"] = include_raw
        return _FakeStructuredModel(self.result, self.captured)


@pytest.mark.asyncio
async def test_knowledge_gap_node_saves_and_builds_messages(monkeypatch):
    saved = {}
    captured = {}
    result = KnowledgeGapDraft(
        title="远程设备报销",
        category="财务",
        suggested_content="1.哪些设备 2.是否审批",
    )

    async def _fake_save(user_id, dept_id, title, question, category, suggested_content):
        saved.update(user_id=user_id, title=title, question=question)

    import app.agent.graph.nodes.knowledge_gap as kg
    monkeypatch.setattr(kg.knowledge_gap_service, "save_gap", _fake_save)
    monkeypatch.setattr(kg, "chat_model", _FakeModel(result, captured))

    state = {"query": "远程办公设备损坏怎么报销",
             "identity": RequestIdentity(user_id="u1", dept_id="d1")}
    update = await knowledge_gap_node(state)

    assert captured["schema"] is KnowledgeGapDraft
    assert captured["include_raw"] is True
    assert saved["user_id"] == "u1"
    assert saved["question"] == "远程办公设备损坏怎么报销"
    assert update["token_usage"] == 77
    assert update["task_messages"][0]["role"] == "system"
    assert update["trace"][0]["agent"] == "knowledge_gap"


@pytest.mark.asyncio
async def test_knowledge_gap_node_survives_save_failure(monkeypatch):
    captured = {}
    result = KnowledgeGapDraft(title="t", category="c", suggested_content="s")

    async def _fake_save(**kwargs):
        raise RuntimeError("db down")

    import app.agent.graph.nodes.knowledge_gap as kg
    monkeypatch.setattr(kg.knowledge_gap_service, "save_gap", _fake_save)
    monkeypatch.setattr(kg, "chat_model", _FakeModel(result, captured))

    state = {"query": "q", "identity": None}
    update = await knowledge_gap_node(state)
    assert "task_messages" in update
