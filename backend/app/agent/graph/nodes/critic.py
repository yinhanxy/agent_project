import json
from typing import Literal, Optional

from pydantic import BaseModel

from app.agent.graph._stream import safe_get_stream_writer
from app.agent.graph.state import AgentState
from app.utils.factory import chat_model, get_chat_model

_DEFAULT_CHAT_MODEL = chat_model

_CRITIC_PROMPT = """你是企业知识库 Agent 的检索证据评估器。系统已对用户问题做过一次知识库检索，但相关度未达阈值。请判断检索到的证据属于哪种情况。

只输出一个 JSON 对象，不要任何额外解释，格式：
{"verdict": "<relevant|needs_rewrite|out_of_scope>", "reason": "<简短中文理由>", "reformulated_query": "<改写后的查询；仅 needs_rewrite 时填写，否则为 null>"}

verdict 取值：
- relevant：证据其实足以回答，只是相关度阈值偏严，可直接据此作答
- needs_rewrite：问题表述/指代导致检索召回不准（如"那它呢"未消解、口语化、缺关键词），改写查询后有望召回——此时必须给出 reformulated_query
- out_of_scope：知识库确实没有相关内容，应如实告知用户并记录缺口

reformulated_query 要求：消解指代、补全主体与关键词、用更书面化的检索式表达；不要编造原文没有的限定条件。"""

# 异常/解析失败时的降级判定：放行（不阻塞主路径），由 finalize 兜底作答
_FALLBACK_VERDICT = {"verdict": "relevant", "reason": "critic 异常，降级放行", "reformulated_query": None}


class CriticVerdict(BaseModel):
    verdict: Literal["relevant", "needs_rewrite", "out_of_scope"]
    reason: str
    reformulated_query: Optional[str] = None


def _verdict_to_dict(obj: "CriticVerdict | dict") -> dict:
    """把结构化输出对象归一为状态中的 critic_verdict 字典；非法 verdict 归一为 relevant。"""
    data = obj.model_dump() if hasattr(obj, "model_dump") else dict(obj)
    verdict = data.get("verdict")
    if verdict not in ("relevant", "needs_rewrite", "out_of_scope"):
        verdict = "relevant"
    return {
        "verdict": verdict,
        "reason": str(data.get("reason", "")),
        "reformulated_query": data.get("reformulated_query"),
    }


def _build_messages(state: AgentState) -> list:
    documents = state.get("documents") or []
    if documents:
        evidence = "\n\n".join(f"【片段{i}】{d[:300]}" for i, d in enumerate(documents, 1))
    else:
        evidence = "（无检索结果）"
    user = (
        f"用户当前问题：{state['query']}\n"
        f"检索最高相关度：{state.get('max_score')}\n"
        f"检索到的证据片段：\n{evidence}"
    )
    return [
        {"role": "system", "content": _CRITIC_PROMPT},
        {"role": "user", "content": user},
    ]


async def critic_node(state: AgentState) -> dict:
    """对 is_enough=False 的检索结果做证据级评估（能改写救援 / 真超范围）。

    critic 走 with_structured_output().ainvoke() 返回完整对象——不经 messages 流，
    LLM token 不会被 astream 的 messages 模式捕获，也不会被 stream_bridge 放行给用户。
    """
    writer = safe_get_stream_writer()
    writer({"kind": "step", "id": "evidence_evaluating", "status": "running",
            "level": "info", "detail": "正在评估检索结果是否足以回答", "title": "评估检索证据"})

    messages = _build_messages(state)
    reformulated = None
    revision_inc = 0
    try:
        model = chat_model if chat_model is not _DEFAULT_CHAT_MODEL else get_chat_model("critic")
        structured = model.with_structured_output(CriticVerdict, include_raw=True)
        result = await structured.ainvoke(messages)
        if result.get("parsing_error"):
            raise result["parsing_error"]
        msg = result.get("raw")
        verdict = _verdict_to_dict(result["parsed"])
        if verdict["verdict"] == "needs_rewrite" and verdict.get("reformulated_query"):
            reformulated = verdict["reformulated_query"]
            revision_inc = 1
        status = "done"
        from app.agent.token_utils import extract_total_tokens, estimate_messages_tokens
        critic_tokens = extract_total_tokens(msg) or estimate_messages_tokens(messages)
    except Exception as e:
        from app.core.logger_handler import logger
        logger.error(f"[Critic] 证据评估失败，降级放行: {e}", exc_info=True)
        verdict = dict(_FALLBACK_VERDICT)
        status = "failed"
        critic_tokens = 0

    writer({"kind": "step", "id": "evidence_evaluated", "status": "done",
            "level": "success", "detail": f"证据评估：{verdict['verdict']}",
            "title": "已完成证据评估"})

    update = {
        "critic_verdict": verdict,
        "token_usage": critic_tokens,
        "trace": [{"agent": "critic_evidence", "status": status,
                   "output": json.dumps(verdict, ensure_ascii=False)}],
    }
    # 仅 needs_rewrite 时才写 reformulated_query / 累加 revision_count（reducer 要求 key 存在才累加）
    if reformulated:
        update["reformulated_query"] = reformulated
    if revision_inc:
        update["revision_count"] = revision_inc
    return update
