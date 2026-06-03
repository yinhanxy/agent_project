import pytest

from app.agent.graph.runner import GraphRunner


async def _fake_astream(state, stream_mode=None):
    class _Chunk:
        def __init__(self, c):
            self.content = c
    yield ("custom", {"kind": "step", "id": "answer_generated",
                      "status": "running", "level": "info", "detail": "正在生成最终回答"})
    yield ("messages", (_Chunk("最终"), {"langgraph_node": "finalize"}))
    yield ("messages", (_Chunk("回答"), {"langgraph_node": "finalize"}))


@pytest.mark.asyncio
async def test_graph_runner_emits_same_schema_as_agentloop(monkeypatch):
    runner = GraphRunner()

    class _FakeGraph:
        def astream(self, state, stream_mode=None):
            return _fake_astream(state, stream_mode=stream_mode)

    monkeypatch.setattr(runner, "_graph", _FakeGraph())

    events = [e async for e in runner.stream("年假制度", history=[], identity=None)]
    types = [e["type"] for e in events]

    # 开头 agent_plan，结尾 done
    assert types[0] == "agent_plan"
    assert types[-1] == "done"
    # 中间有 token，且拼接为完整回答
    tokens = "".join(e["data"] for e in events if e["type"] == "token")
    assert tokens == "最终回答"
    # done 帧字段齐全
    done = events[-1]
    assert "steps" in done and "tokens" in done and "citations" in done


@pytest.mark.asyncio
async def test_graph_runner_done_carries_citations_from_state(monkeypatch):
    runner = GraphRunner()

    class _Chunk:
        def __init__(self, c):
            self.content = c

    async def _fake_astream(state, stream_mode=None):
        yield ("messages", (_Chunk("答"), {"langgraph_node": "finalize"}))
        yield ("values", {"citations": [{"filename": "a.pdf", "score": 0.8}],
                          "final_answer": "答"})

    class _FakeGraph:
        def astream(self, state, stream_mode=None):
            return _fake_astream(state, stream_mode=stream_mode)

    monkeypatch.setattr(runner, "_graph", _FakeGraph())

    events = [e async for e in runner.stream("q", history=[], identity=None)]
    done = events[-1]
    assert done["type"] == "done"
    assert done["citations"] == [{"filename": "a.pdf", "score": 0.8}]
