import pytest

import app.agent.graph.nodes.coordinator as co
import app.agent.graph.nodes.knowledge as kn
import app.agent.graph.nodes.critic as cr
import app.agent.graph.nodes.finalize as fz
from app.agent.graph.nodes.coordinator import CoordinatorPlan
from app.agent.graph.nodes.critic import CriticVerdict
from app.agent.graph.runner import GraphRunner


class _Raw:
    usage_metadata = {"total_tokens": 10}


class _StructFake:
    def __init__(self, parsed):
        self._p = parsed

    async def ainvoke(self, messages):
        return {"raw": _Raw(), "parsed": self._p, "parsing_error": None}


class _ModelFake:
    def __init__(self, parsed):
        self._p = parsed

    def with_structured_output(self, schema, include_raw=False):
        return _StructFake(self._p)


class _FinalizeMsg:
    content = "这是基于改写检索后的最终回答"


class _FinalizeModel:
    async def ainvoke(self, messages):
        return _FinalizeMsg()


@pytest.mark.asyncio
async def test_critic_loop_end_to_end(monkeypatch):
    monkeypatch.setenv("AGENT_CRITIC_ENABLE", "true")
    monkeypatch.setenv("AGENT_CRITIC_MAX_REVISIONS", "1")

    monkeypatch.setattr(co, "chat_model", _ModelFake(
        CoordinatorPlan(task_type="knowledge_qa", need_retrieval=True, reason="问答")))
    monkeypatch.setattr(cr, "chat_model", _ModelFake(
        CriticVerdict(verdict="needs_rewrite", reason="指代未消解",
                      reformulated_query="2025版差旅报销上限")))
    monkeypatch.setattr(fz, "chat_model", _FinalizeModel())

    calls = {"n": 0}

    async def _fake_get(query, filter_meta=None):
        calls["n"] += 1
        if calls["n"] == 1:                      # 首检索：低置信
            return {"documents": [], "citations": [], "is_enough": False, "max_score": 0.1}
        return {                                  # 重检索：命中
            "documents": ["2025版差旅报销上限为800元"],
            "citations": [{"filename": "差旅2025.pdf", "score": 0.92}],
            "is_enough": True, "max_score": 0.92,
        }

    monkeypatch.setattr(kn.rag_service, "get_documents_for_agent", _fake_get)

    runner = GraphRunner()    # 在 env 设好后编译 → 启用 critic
    events = [e async for e in runner.stream(
        "那它2025版呢", history=[("差旅2023版上限", "上限500元")], identity=None)]

    # 进度帧含 critic 评估与重检索
    step_ids = [e["data"].get("id") for e in events if e["type"] == "agent_step_update"]
    assert "evidence_evaluating" in step_ids
    assert "knowledge_refetching" in step_ids

    # done.steps（trace 摘要）含 critic_evidence 与 knowledge_retry
    done = events[-1]
    assert done["type"] == "done"
    agents = [s["agent"] for s in done["steps"]]
    assert "critic_evidence" in agents
    assert "knowledge_retry" in agents

    # 确实重检索了一次（共两次检索调用）
    assert calls["n"] == 2

    # 用户最终看到回答（finalize 经 runner 兜底/流式产出）
    tokens = "".join(e["data"] for e in events if e["type"] == "token")
    assert tokens == "这是基于改写检索后的最终回答"
