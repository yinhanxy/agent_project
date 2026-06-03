import pytest

from app.agent.graph.nodes.task import task_node


@pytest.mark.asyncio
async def test_task_node_uses_compare_tool():
    state = {
        "query": "新旧报销制度区别",
        "plan": {"task_type": "document_compare"},
        "documents": ["旧版500", "新版600"],
    }
    update = await task_node(state)
    msgs = update["task_messages"]
    assert msgs[0]["role"] == "system" and "表格" in msgs[0]["content"]
    assert "旧版500" in msgs[1]["content"]
    assert update["trace"][0]["agent"] == "task"


@pytest.mark.asyncio
async def test_task_node_uses_report_tool():
    state = {
        "query": "售后流程报告",
        "plan": {"task_type": "report_generation"},
        "documents": ["售后政策"],
    }
    update = await task_node(state)
    assert "报告" in update["task_messages"][0]["content"]


@pytest.mark.asyncio
async def test_task_node_unknown_type_yields_no_task_messages():
    # 防御：理论上路由不会把非任务类型导到 task，但若发生应安全降级（不设 task_messages）
    state = {"query": "x", "plan": {"task_type": "knowledge_qa"}, "documents": ["d"]}
    update = await task_node(state)
    assert "task_messages" not in update or not update.get("task_messages")
