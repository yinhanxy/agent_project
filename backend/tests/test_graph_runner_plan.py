import pytest
import app.agent.graph.nodes.coordinator as co
import app.agent.graph.nodes.knowledge as kn
import app.agent.graph.nodes.finalize as fz
from app.agent.graph.nodes.coordinator import CoordinatorPlan
from app.agent.graph.runner import GraphRunner


class _Raw:
    usage_metadata = {"total_tokens": 10}


class _StructFake:
    def __init__(self, parsed): self._p = parsed
    async def ainvoke(self, messages):
        return {"raw": _Raw(), "parsed": self._p, "parsing_error": None}


class _ModelFake:
    def __init__(self, parsed): self._p = parsed
    def with_structured_output(self, schema, include_raw=False):
        return _StructFake(self._p)


class _FinalizeMsg:
    content = "回答"


class _FinalizeModel:
    async def ainvoke(self, messages): return _FinalizeMsg()


@pytest.mark.asyncio
async def test_done_frame_exposes_plan_task_type(monkeypatch):
    monkeypatch.setenv("AGENT_CRITIC_ENABLE", "false")
    monkeypatch.setattr(co, "chat_model", _ModelFake(
        CoordinatorPlan(task_type="document_compare", need_retrieval=True, reason="对比")))
    monkeypatch.setattr(fz, "chat_model", _FinalizeModel())

    async def _fake_get(query, filter_meta=None):
        return {"documents": ["x"], "citations": [{"filename": "a.md", "score": 0.9}],
                "is_enough": True, "max_score": 0.9}
    monkeypatch.setattr(kn.rag_service, "get_documents_for_agent", _fake_get)

    runner = GraphRunner()
    events = [e async for e in runner.stream("对比2023和2025版", history=[], identity=None)]
    done = next(e for e in reversed(events) if e["type"] == "done")
    assert done.get("plan", {}).get("task_type") == "document_compare"
