import pytest

from app.agent.graph.nodes.task import route_after_knowledge


def test_route_to_task_when_compare_with_docs():
    state = {"plan": {"task_type": "document_compare"}, "documents": ["d"]}
    assert route_after_knowledge(state) == "task"


def test_route_to_finalize_for_plain_qa():
    state = {"plan": {"task_type": "knowledge_qa"}, "documents": ["d"]}
    assert route_after_knowledge(state) == "finalize"


def test_route_to_finalize_when_task_type_but_no_docs():
    # 任务类型但没检索到文档：不强行执行任务，退回 finalize（由其说明信息不足）
    state = {"plan": {"task_type": "report_generation"}, "documents": []}
    assert route_after_knowledge(state) == "finalize"


@pytest.mark.asyncio
async def test_graph_routes_compare_through_task_node(monkeypatch):
    """document_compare + 有文档：图应经过 task 节点，finalize 收到 task_messages。"""
    import app.agent.graph.nodes.coordinator as co
    import app.agent.graph.nodes.knowledge as kn
    import app.agent.graph.nodes.finalize as fz

    class _Msg:
        def __init__(self, c):
            self.content = c

    async def _fake_get_docs(query, filter_meta=None):
        return {"documents": ["旧版500", "新版600"], "citations": [], "summary": "", "error": None}

    captured = {}

    async def _fake_final(messages):
        captured["messages"] = messages
        return _Msg("| 对比项 | 旧 | 新 |")

    class _Coord:
        def with_structured_output(self, schema, include_raw=False):
            class _Structured:
                async def ainvoke(self, _messages):
                    return {
                        "raw": _Msg(""),
                        "parsed": schema(
                            task_type="document_compare",
                            need_retrieval=True,
                            reason="对比",
                        ),
                        "parsing_error": None,
                    }
            return _Structured()

    class _Final:
        ainvoke = staticmethod(_fake_final)

    monkeypatch.setattr(co, "chat_model", _Coord())
    monkeypatch.setattr(fz, "chat_model", _Final())
    monkeypatch.setattr(kn.rag_service, "get_documents_for_agent", _fake_get_docs)

    from app.agent.graph.build import build_graph
    graph = build_graph()
    result = await graph.ainvoke({"query": "新旧报销制度区别", "history": [], "trace": []})

    assert "表格" in captured["messages"][0]["content"]
    assert result["final_answer"] == "| 对比项 | 旧 | 新 |"
