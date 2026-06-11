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


@pytest.mark.asyncio
async def test_finalize_prefers_task_messages(monkeypatch):
    captured = {}

    async def _fake_ainvoke(messages):
        captured["messages"] = messages
        return _FakeMsg("对比表内容")

    import app.agent.graph.nodes.finalize as fz

    class _FakeChatModel:
        ainvoke = staticmethod(_fake_ainvoke)

    monkeypatch.setattr(fz, "chat_model", _FakeChatModel())

    task_msgs = [{"role": "system", "content": "对比助手"},
                 {"role": "user", "content": "对比文档"}]
    state = {"query": "随便", "documents": ["d"], "task_messages": task_msgs}
    update = await finalize_node(state)

    assert captured["messages"] == task_msgs
    assert update["final_answer"] == "对比表内容"


@pytest.mark.asyncio
async def test_finalize_includes_history(monkeypatch):
    captured = {}

    async def _fake_ainvoke(messages):
        captured["messages"] = messages
        return _FakeMsg("基于上下文的回答")

    import app.agent.graph.nodes.finalize as fz

    class _FakeChatModel:
        ainvoke = staticmethod(_fake_ainvoke)

    monkeypatch.setattr(fz, "chat_model", _FakeChatModel())

    state = {
        "query": "那它2025版改了什么",
        "documents": [],
        "history": [("2023版报销上限多少", "上限是500元")],
    }
    await finalize_node(state)

    roles = [m["role"] for m in captured["messages"]]
    # system + 历史(user,assistant) + 当前 user
    assert roles == ["system", "user", "assistant", "user"]
    assert captured["messages"][1]["content"] == "2023版报销上限多少"
    assert captured["messages"][2]["content"] == "上限是500元"
    assert "那它2025版改了什么" in captured["messages"][-1]["content"]


def test_finalize_injects_strict_citation_when_critic_relevant():
    from app.agent.graph.nodes.finalize import _build_messages
    msgs = _build_messages({
        "query": "年假几天",
        "documents": ["年假为5天"],
        "critic_verdict": {"verdict": "relevant"},
    })
    joined = " ".join(m["content"] for m in msgs)
    assert "文档未提及" in joined        # 注入了严格引用指令
    # 严格指令内联进最终 user 消息，不产生连续两条同角色消息
    roles = [m["role"] for m in msgs]
    assert all(roles[i] != roles[i + 1] for i in range(len(roles) - 1))


def test_finalize_no_strict_citation_without_critic():
    from app.agent.graph.nodes.finalize import _build_messages
    msgs = _build_messages({"query": "年假几天", "documents": ["年假为5天"]})
    joined = " ".join(m["content"] for m in msgs)
    assert "文档未提及" not in joined    # 无 critic_verdict 时不注入
