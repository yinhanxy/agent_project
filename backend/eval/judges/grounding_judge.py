"""grounding faithfulness：回答的事实陈述是否都能在检索文档里找到依据。"""
from typing import Optional
from pydantic import BaseModel


class GroundingVerdict(BaseModel):
    total_claims: int                 # 回答里可核查的事实性陈述数
    unsupported_claims: list[str]     # 其中在文档里找不到依据的
    reasoning: str = ""


def faithfulness_score(total_claims: int, unsupported: int) -> Optional[float]:
    if not total_claims:
        return None
    return max(0.0, (total_claims - unsupported) / total_claims)


_SYSTEM = (
    "你是事实核查员。给定一段回答和若干文档片段。先数出回答中可核查的事实性陈述总数，"
    "再列出其中无法在文档片段中找到依据的陈述。不要把常识或措辞性语句算作事实陈述。"
)


async def judge_faithfulness(model, answer: str, documents: list) -> Optional[float]:
    if not (answer or "").strip():
        return None
    ctx = "\n\n".join(f"【片段{i}】{d}" for i, d in enumerate(documents or [], 1)) or "（无检索文档）"
    user = f"回答：{answer}\n\n文档片段：\n{ctx}"
    structured = model.with_structured_output(GroundingVerdict)
    v = await structured.ainvoke(
        [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}])
    return faithfulness_score(v.total_claims, len(v.unsupported_claims or []))
