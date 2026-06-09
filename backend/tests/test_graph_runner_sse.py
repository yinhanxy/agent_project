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


@pytest.mark.asyncio
async def test_graph_runner_emits_usage_with_estimation(monkeypatch):
    """没有精确 usage 时，runner 应仍然发 usage 事件且 done.tokens > 0（估算口径）。"""
    runner = GraphRunner()

    class _Chunk:
        def __init__(self, c):
            self.content = c

    async def _astream(state, stream_mode=None):
        # 多段较长内容，确保触发节流阈值（>=20 字符）至少一次
        yield ("messages", (_Chunk("这是一段足够长的最终回答开头"), {"langgraph_node": "finalize"}))
        yield ("messages", (_Chunk("继续输出更多内容用于触发 usage 节流事件"), {"langgraph_node": "finalize"}))

    class _FakeGraph:
        def astream(self, state, stream_mode=None):
            return _astream(state, stream_mode=stream_mode)

    monkeypatch.setattr(runner, "_graph", _FakeGraph())

    events = [e async for e in runner.stream("员工请假流程是什么", history=[], identity=None)]
    usage_events = [e for e in events if e["type"] == "usage"]
    # 至少有一条思考期初始 usage + 一条流式 usage
    assert len(usage_events) >= 2
    # 思考期那条应大于 0（query 估算）
    assert usage_events[0]["tokens"] > 0
    # 流式 usage 单调不下降
    token_seq = [e["tokens"] for e in usage_events]
    assert token_seq == sorted(token_seq)
    # done.tokens 应大于初始估算（说明把回答内容也算进来了）
    done = events[-1]
    assert done["type"] == "done"
    assert done["tokens"] >= usage_events[0]["tokens"]
    assert done["tokens"] > 0


@pytest.mark.asyncio
async def test_graph_runner_uses_accurate_usage_metadata_when_available(monkeypatch):
    """chunk 上带 usage_metadata 时，done.tokens 应使用精确值而非估算。"""
    runner = GraphRunner()

    class _Chunk:
        def __init__(self, c, usage_metadata=None):
            self.content = c
            if usage_metadata is not None:
                self.usage_metadata = usage_metadata

    async def _astream(state, stream_mode=None):
        yield ("messages", (_Chunk("回答"), {"langgraph_node": "finalize"}))
        # 最后一帧带精确 usage（LangChain 标准）
        yield ("messages", (
            _Chunk("", usage_metadata={"input_tokens": 100, "output_tokens": 23, "total_tokens": 123}),
            {"langgraph_node": "finalize"},
        ))

    class _FakeGraph:
        def astream(self, state, stream_mode=None):
            return _astream(state, stream_mode=stream_mode)

    monkeypatch.setattr(runner, "_graph", _FakeGraph())

    events = [e async for e in runner.stream("q", history=[], identity=None)]
    done = events[-1]
    assert done["type"] == "done"
    assert done["tokens"] == 123  # 精确值，不被估算覆盖


@pytest.mark.asyncio
async def test_graph_runner_persists_trace_and_done_steps(monkeypatch):
    """传 session_id 时：trace 经 agent_trace_service 落库，done.steps 为 trace 摘要。"""
    runner = GraphRunner()

    class _Chunk:
        def __init__(self, c):
            self.content = c

    async def _astream(state, stream_mode=None):
        yield ("messages", (_Chunk("答"), {"langgraph_node": "finalize"}))
        yield ("values", {
            "final_answer": "答",
            "trace": [
                {"agent": "coordinator", "status": "done", "output": "{}"},
                {"agent": "finalize", "status": "done", "output": "答"},
            ],
        })

    class _FakeGraph:
        def astream(self, state, stream_mode=None):
            return _astream(state, stream_mode=stream_mode)

    monkeypatch.setattr(runner, "_graph", _FakeGraph())

    saved = {}

    async def _fake_save(session_id, trace):
        saved["session_id"] = session_id
        saved["trace"] = trace

    from app.services.agent_trace_service import agent_trace_service
    monkeypatch.setattr(agent_trace_service, "save_traces", _fake_save)

    events = [e async for e in runner.stream("q", history=[], identity=None, session_id="sid-1")]
    done = events[-1]
    assert done["type"] == "done"
    assert done["steps"] == [
        {"agent": "coordinator", "status": "done"},
        {"agent": "finalize", "status": "done"},
    ]
    assert saved["session_id"] == "sid-1"
    assert len(saved["trace"]) == 2
