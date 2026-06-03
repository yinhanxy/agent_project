import pytest

from app.agent.graph import nodes as _nodes_pkg  # noqa: F401 确保包存在
from app.agent.graph.nodes.finalize import finalize_node


class _FakeMsg:
    def __init__(self, content):
        self.content = content


@pytest.mark.asyncio
async def test_finalize_node_returns_final_answer(monkeypatch):
    async def _fake_ainvoke(_messages):
        return _FakeMsg("这是最终回答")

    import app.agent.graph.nodes.finalize as fz

    class _FakeChatModel:
        ainvoke = staticmethod(_fake_ainvoke)

    monkeypatch.setattr(fz, "chat_model", _FakeChatModel())

    state = {"query": "公司年假制度是什么", "documents": [], "history": []}
    update = await finalize_node(state)

    assert update["final_answer"] == "这是最终回答"
    assert isinstance(update["trace"], list)
    assert update["trace"][0]["agent"] == "finalize"
