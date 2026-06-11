from app.agent.graph.nodes.task import route_after_knowledge
from app.agent.graph.nodes.critic import route_after_critic


def test_route_after_knowledge_low_confidence_goes_to_critic(monkeypatch):
    monkeypatch.setenv("AGENT_CRITIC_ENABLE", "true")
    state = {"is_enough": False, "plan": {"task_type": "knowledge_qa"}}
    assert route_after_knowledge(state) == "critic"


def test_route_after_knowledge_critic_disabled_falls_back_to_gap(monkeypatch):
    monkeypatch.setenv("AGENT_CRITIC_ENABLE", "false")
    state = {"is_enough": False, "plan": {"task_type": "knowledge_qa"}}
    assert route_after_knowledge(state) == "knowledge_gap"


def test_route_after_knowledge_enough_qa_goes_to_finalize(monkeypatch):
    monkeypatch.setenv("AGENT_CRITIC_ENABLE", "true")
    state = {"is_enough": True, "plan": {"task_type": "knowledge_qa"}, "documents": ["d"]}
    assert route_after_knowledge(state) == "finalize"


def test_route_after_knowledge_enough_compare_goes_to_task(monkeypatch):
    monkeypatch.setenv("AGENT_CRITIC_ENABLE", "true")
    state = {"is_enough": True, "plan": {"task_type": "document_compare"}, "documents": ["d"]}
    assert route_after_knowledge(state) == "task"


def test_route_after_knowledge_coordinator_gap_still_gaps(monkeypatch):
    # coordinator 显式判 knowledge_gap 且 is_enough=True：仍直接走 gap（不进 critic）
    monkeypatch.setenv("AGENT_CRITIC_ENABLE", "true")
    state = {"is_enough": True, "plan": {"task_type": "knowledge_gap"}, "documents": ["d"]}
    assert route_after_knowledge(state) == "knowledge_gap"


def test_route_after_critic_relevant_to_finalize():
    state = {"critic_verdict": {"verdict": "relevant"},
             "plan": {"task_type": "knowledge_qa"}, "documents": ["d"]}
    assert route_after_critic(state) == "finalize"


def test_route_after_critic_relevant_compare_to_task():
    state = {"critic_verdict": {"verdict": "relevant"},
             "plan": {"task_type": "document_compare"}, "documents": ["d"]}
    assert route_after_critic(state) == "task"


def test_route_after_critic_needs_rewrite_within_budget(monkeypatch):
    monkeypatch.setenv("AGENT_CRITIC_MAX_REVISIONS", "1")
    # critic 已把 revision_count 累加到 1（≤ 上限）→ 重检索
    state = {"critic_verdict": {"verdict": "needs_rewrite"}, "revision_count": 1}
    assert route_after_critic(state) == "knowledge"


def test_route_after_critic_needs_rewrite_over_budget(monkeypatch):
    monkeypatch.setenv("AGENT_CRITIC_MAX_REVISIONS", "1")
    # 第二次仍 needs_rewrite，revision_count 累到 2（> 上限）→ 强制 gap
    state = {"critic_verdict": {"verdict": "needs_rewrite"}, "revision_count": 2}
    assert route_after_critic(state) == "knowledge_gap"


def test_route_after_critic_needs_rewrite_zero_budget_to_gap(monkeypatch):
    monkeypatch.setenv("AGENT_CRITIC_MAX_REVISIONS", "0")
    # 上限 0：做证据评估但不允许改写重检索（revision_count=1 > 0）→ 直接 gap
    state = {"critic_verdict": {"verdict": "needs_rewrite"}, "revision_count": 1}
    assert route_after_critic(state) == "knowledge_gap"


def test_route_after_critic_out_of_scope_to_gap():
    assert route_after_critic({"critic_verdict": {"verdict": "out_of_scope"}}) == "knowledge_gap"
