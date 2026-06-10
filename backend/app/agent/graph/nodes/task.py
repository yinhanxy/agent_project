from app.agent.graph._stream import safe_get_stream_writer
from app.agent.graph.critic_config import critic_enabled
from app.agent.graph.state import AgentState
from app.tools import compare_tool, report_tool, form_tool

# task_type → 对应任务 tool（每个 tool 都有 build_messages(query, documents)）
_TOOL_MAP = {
    "document_compare": compare_tool,
    "report_generation": report_tool,
    "document_generation": form_tool,
}

# 需要走 Task 节点的任务类型（供 route_after_knowledge 使用）
TASK_TYPES_NEEDING_TASK = frozenset(_TOOL_MAP.keys())

_STEP_TITLE = {
    "document_compare": "生成文档对比",
    "report_generation": "生成报告",
    "document_generation": "生成申请文本",
}


async def task_node(state: AgentState) -> dict:
    """按 task_type 选 tool，构造任务专属 messages 写入 state；不调 LLM（生成留给 finalize）。"""
    task_type = (state.get("plan") or {}).get("task_type", "")
    tool = _TOOL_MAP.get(task_type)
    if tool is None:
        # 防御性降级：非任务类型不产生 task_messages，finalize 走默认问答
        return {"trace": [{"agent": "task", "status": "skipped",
                           "output": f"no tool for task_type={task_type}"}]}

    title = _STEP_TITLE.get(task_type, "执行任务")
    writer = safe_get_stream_writer()
    writer({"kind": "step", "id": "task_execute", "status": "running",
            "level": "info", "detail": f"正在{title}", "title": title})

    messages = tool.build_messages(state["query"], state.get("documents") or [])

    writer({"kind": "step", "id": "task_execute", "status": "done",
            "level": "success", "detail": f"已准备{title}", "title": title})

    return {
        "task_messages": messages,
        "trace": [{"agent": "task", "status": "done", "output": f"task_type={task_type}"}],
    }


def route_after_knowledge(state: AgentState) -> str:
    """knowledge 之后的路由。

    is_enough=False：critic 开启则交给证据评估（可改写救援）；关闭则沿用原行为直接 gap。
    is_enough=True：coordinator 显式判 gap 优先；否则有任务工具且有文档走 task，余下 finalize。
    """
    plan = state.get("plan") or {}
    if not state.get("is_enough", True):
        return "critic" if critic_enabled() else "knowledge_gap"
    if plan.get("task_type") == "knowledge_gap":
        return "knowledge_gap"
    if plan.get("task_type") in TASK_TYPES_NEEDING_TASK and state.get("documents"):
        return "task"
    return "finalize"
