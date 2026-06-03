from app.agent.graph.nodes.coordinator import route_after_coordinator


def test_route_to_knowledge_when_need_retrieval():
    state = {"plan": {"task_type": "knowledge_qa", "need_retrieval": True}}
    assert route_after_coordinator(state) == "knowledge"


def test_route_to_finalize_when_no_retrieval():
    state = {"plan": {"task_type": "knowledge_qa", "need_retrieval": False}}
    assert route_after_coordinator(state) == "finalize"


def test_route_defaults_to_knowledge_when_plan_missing():
    # 没有 plan 时保守走检索（不漏检索）
    assert route_after_coordinator({}) == "knowledge"
