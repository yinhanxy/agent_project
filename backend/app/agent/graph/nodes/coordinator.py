import json
import re

from app.agent.graph._stream import safe_get_stream_writer
from app.agent.graph.state import AgentState
from app.utils.factory import chat_model

# 合法任务类型（与设计文档一致）；非法值归一为 unknown
_TASK_TYPES = {
    "knowledge_qa", "document_compare", "document_generation",
    "report_generation", "knowledge_gap", "unknown",
}

_COORDINATOR_PROMPT = """你是企业知识库 Agent 的任务协调器。判断用户问题属于哪种任务类型，以及是否需要检索知识库。

只输出一个 JSON 对象，不要任何额外解释，格式：
{"task_type": "<类型>", "need_retrieval": <true|false>, "reason": "<简短中文理由>"}

task_type 取值：
- knowledge_qa：普通知识问答
- document_compare：多文档/新旧版对比
- document_generation：生成申请/说明等文本
- report_generation：生成结构化报告
- knowledge_gap：明显超出知识库范围、需记录缺口
- unknown：无法识别

need_retrieval：除非是与企业知识完全无关的闲聊，否则一律为 true。"""

# 兜底 plan：分类失败时保守走检索（行为退化为 Phase 2）
_FALLBACK_PLAN = {"task_type": "knowledge_qa", "need_retrieval": True,
                  "reason": "分类失败，默认走检索"}


def _parse_plan(text: str) -> dict:
    """从 LLM 输出中提取 JSON plan，健壮处理代码块/多余文字/非法值。"""
    if not text:
        return dict(_FALLBACK_PLAN)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return dict(_FALLBACK_PLAN)
    try:
        data = json.loads(match.group(0))
    except (json.JSONDecodeError, ValueError):
        return dict(_FALLBACK_PLAN)

    task_type = data.get("task_type")
    if task_type not in _TASK_TYPES:
        task_type = "unknown"
    return {
        "task_type": task_type,
        "need_retrieval": bool(data.get("need_retrieval", True)),
        "reason": str(data.get("reason", "")),
    }


async def coordinator_node(state: AgentState) -> dict:
    """判定任务类型与是否需要检索。LLM token 因节点名非 finalize 被 bridge 过滤，不泄漏。"""
    writer = safe_get_stream_writer()
    writer({"kind": "step", "id": "task_understood", "status": "running",
            "level": "info", "detail": "正在识别任务类型", "title": "识别任务类型"})

    messages = [
        {"role": "system", "content": _COORDINATOR_PROMPT},
        {"role": "user", "content": state["query"]},
    ]
    msg = await chat_model.ainvoke(messages)
    text = msg.content if hasattr(msg, "content") else str(msg)
    plan = _parse_plan(text)

    writer({"kind": "step", "id": "task_understood", "status": "done",
            "level": "success", "detail": f"识别为：{plan['task_type']}",
            "title": "已识别任务类型"})

    return {
        "plan": plan,
        "trace": [{"agent": "coordinator", "status": "done",
                   "output": json.dumps(plan, ensure_ascii=False)}],
    }


def route_after_coordinator(state: AgentState) -> str:
    """条件边：need_retrieval 为真走 knowledge，否则直接 finalize。缺 plan 时保守走 knowledge。"""
    plan = state.get("plan") or {}
    return "knowledge" if plan.get("need_retrieval", True) else "finalize"
