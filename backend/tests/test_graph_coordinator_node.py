import pytest

from app.agent.graph.nodes.coordinator import coordinator_node, _parse_plan


def test_parse_plan_plain_json():
    text = '{"task_type": "document_compare", "need_retrieval": true, "reason": "对比新旧制度"}'
    plan = _parse_plan(text)
    assert plan["task_type"] == "document_compare"
    assert plan["need_retrieval"] is True
    assert plan["reason"] == "对比新旧制度"


def test_parse_plan_with_code_fence_and_extra_text():
    text = '好的，分析如下：\n```json\n{"task_type": "knowledge_qa", "need_retrieval": true, "reason": "普通问答"}\n```\n以上。'
    plan = _parse_plan(text)
    assert plan["task_type"] == "knowledge_qa"
    assert plan["need_retrieval"] is True


def test_parse_plan_unknown_task_type_falls_back():
    text = '{"task_type": "啥也不是", "need_retrieval": false, "reason": "x"}'
    plan = _parse_plan(text)
    assert plan["task_type"] == "unknown"
    assert plan["need_retrieval"] is False


def test_parse_plan_garbage_falls_back_to_retrieval():
    plan = _parse_plan("这不是 JSON")
    assert plan["task_type"] == "knowledge_qa"
    assert plan["need_retrieval"] is True


class _FakeMsg:
    def __init__(self, content):
        self.content = content


@pytest.mark.asyncio
async def test_coordinator_node_writes_plan(monkeypatch):
    async def _fake_ainvoke(_messages):
        return _FakeMsg('{"task_type": "report_generation", "need_retrieval": true, "reason": "要生成报告"}')

    import app.agent.graph.nodes.coordinator as co

    class _FakeChatModel:
        ainvoke = staticmethod(_fake_ainvoke)

    monkeypatch.setattr(co, "chat_model", _FakeChatModel())

    update = await coordinator_node({"query": "根据售后政策生成报告"})
    assert update["plan"]["task_type"] == "report_generation"
    assert update["plan"]["need_retrieval"] is True
    assert update["trace"][0]["agent"] == "coordinator"
