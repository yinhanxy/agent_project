import pytest

from app.agent.graph.nodes.task import route_after_knowledge


def test_route_to_gap_when_not_enough(monkeypatch):
    monkeypatch.setenv("AGENT_CRITIC_ENABLE", "false")   # critic 关闭时回退直连 gap
    state = {"plan": {"task_type": "knowledge_qa"}, "documents": [], "is_enough": False}
    assert route_after_knowledge(state) == "knowledge_gap"


def test_route_to_gap_when_coordinator_says_gap():
    state = {"plan": {"task_type": "knowledge_gap"}, "documents": ["d"], "is_enough": True}
    assert route_after_knowledge(state) == "knowledge_gap"


def test_gap_priority_over_task(monkeypatch):
    monkeypatch.setenv("AGENT_CRITIC_ENABLE", "false")   # critic 关闭时回退直连 gap
    state = {"plan": {"task_type": "document_compare"}, "documents": [], "is_enough": False}
    assert route_after_knowledge(state) == "knowledge_gap"


def test_route_to_task_still_works():
    state = {"plan": {"task_type": "document_compare"}, "documents": ["d"], "is_enough": True}
    assert route_after_knowledge(state) == "task"


def test_route_to_finalize_for_plain_qa():
    state = {"plan": {"task_type": "knowledge_qa"}, "documents": ["d"], "is_enough": True}
    assert route_after_knowledge(state) == "finalize"


@pytest.mark.asyncio
async def test_graph_routes_through_gap_node_when_no_docs(monkeypatch):
    """is_enough=False（无文档）：critic 关闭时图应经过 knowledge_gap 节点，落库被调用。"""
    monkeypatch.setenv("AGENT_CRITIC_ENABLE", "false")
    import app.agent.graph.nodes.coordinator as co
    import app.agent.graph.nodes.knowledge as kn
    import app.agent.graph.nodes.finalize as fz
    import app.agent.graph.nodes.knowledge_gap as kg

    class _Msg:
        def __init__(self, c):
            self.content = c

    async def _fake_coord(_m):
        return _Msg('{"task_type": "knowledge_qa", "need_retrieval": true, "reason": "x"}')

    async def _fake_get_docs(query, filter_meta=None):
        return {"documents": [], "citations": [], "summary": "", "error": None}

    async def _fake_gap_invoke(_m):
        return _Msg('{"title":"缺口","category":"c","suggested_content":"s"}')

    async def _fake_final(_m):
        return _Msg("知识库暂无依据，已记录缺口。")

    saved = {"hit": False}

    async def _fake_save(**kwargs):
        saved["hit"] = True

    monkeypatch.setattr(co, "chat_model", type("M", (), {"ainvoke": staticmethod(_fake_coord)})())
    monkeypatch.setattr(kn.rag_service, "get_documents_for_agent", _fake_get_docs)
    monkeypatch.setattr(kg, "chat_model", type("M", (), {"ainvoke": staticmethod(_fake_gap_invoke)})())
    monkeypatch.setattr(kg.knowledge_gap_service, "save_gap", _fake_save)
    monkeypatch.setattr(fz, "chat_model", type("M", (), {"ainvoke": staticmethod(_fake_final)})())

    from app.agent.graph.build import build_graph
    graph = build_graph()
    result = await graph.ainvoke({"query": "远程设备报销", "history": [], "trace": []})

    assert saved["hit"] is True
    assert result["final_answer"] == "知识库暂无依据，已记录缺口。"
