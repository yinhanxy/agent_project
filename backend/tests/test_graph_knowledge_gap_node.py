import pytest

from app.agent.graph.nodes.knowledge_gap import knowledge_gap_node, _parse_gap
from app.utils.auth_utils import RequestIdentity


def test_parse_gap_plain_json():
    text = '{"title": "设备报销", "category": "财务", "suggested_content": "1.哪些可报"}'
    gap = _parse_gap(text, fallback_question="远程设备损坏报销")
    assert gap["title"] == "设备报销" and gap["category"] == "财务"


def test_parse_gap_fallback_on_garbage():
    gap = _parse_gap("不是JSON", fallback_question="远程设备损坏报销")
    assert gap["title"]
    assert gap["category"] == "unknown"
    assert gap["suggested_content"]


class _FakeMsg:
    def __init__(self, content):
        self.content = content


@pytest.mark.asyncio
async def test_knowledge_gap_node_saves_and_builds_messages(monkeypatch):
    saved = {}

    async def _fake_save(user_id, dept_id, title, question, category, suggested_content):
        saved.update(user_id=user_id, title=title, question=question)

    async def _fake_ainvoke(_messages):
        return _FakeMsg('{"title": "远程设备报销", "category": "财务", "suggested_content": "1.哪些设备 2.是否审批"}')

    import app.agent.graph.nodes.knowledge_gap as kg
    monkeypatch.setattr(kg.knowledge_gap_service, "save_gap", _fake_save)

    class _FakeModel:
        ainvoke = staticmethod(_fake_ainvoke)
    monkeypatch.setattr(kg, "chat_model", _FakeModel())

    state = {"query": "远程办公设备损坏怎么报销",
             "identity": RequestIdentity(user_id="u1", dept_id="d1")}
    update = await knowledge_gap_node(state)

    assert saved["user_id"] == "u1"
    assert saved["question"] == "远程办公设备损坏怎么报销"
    assert update["task_messages"][0]["role"] == "system"
    assert update["trace"][0]["agent"] == "knowledge_gap"


@pytest.mark.asyncio
async def test_knowledge_gap_node_survives_save_failure(monkeypatch):
    async def _fake_save(**kwargs):
        raise RuntimeError("db down")

    async def _fake_ainvoke(_messages):
        return _FakeMsg('{"title":"t","category":"c","suggested_content":"s"}')

    import app.agent.graph.nodes.knowledge_gap as kg
    monkeypatch.setattr(kg.knowledge_gap_service, "save_gap", _fake_save)

    class _FakeModel:
        ainvoke = staticmethod(_fake_ainvoke)
    monkeypatch.setattr(kg, "chat_model", _FakeModel())

    state = {"query": "q", "identity": None}
    update = await knowledge_gap_node(state)
    assert "task_messages" in update
