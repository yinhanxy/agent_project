"""grounding faithfulness：回答的事实陈述是否都能在检索文档里找到依据。"""
import json
from typing import Optional
from pydantic import BaseModel, field_validator


def _coerce_str_list(v):
    """容错：不同 judge 模型的结构化输出可能把 list 字段返回成字符串化的 JSON
    数组（如 '\\n["a","b"]\\n'）或纯文本，而非真正的 list。统一归一化成 list[str]。
    """
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return []
        try:
            parsed = json.loads(s)
            return [str(x) for x in parsed] if isinstance(parsed, list) else [str(parsed)]
        except Exception:
            return [s]
    return [str(v)]


def _coerce_int(v):
    """容错：judge 可能把 int 字段返回成字符串（如 "3"）。无法解析时退 0。"""
    if isinstance(v, str):
        s = v.strip()
        try:
            return int(float(s)) if s else 0
        except Exception:
            return 0
    return v


class GroundingVerdict(BaseModel):
    total_claims: int = 0             # 回答里可核查的事实性陈述数
    unsupported_claims: list[str] = []  # 其中在文档里找不到依据的
    reasoning: str = ""

    @field_validator("unsupported_claims", mode="before")
    @classmethod
    def _v_unsupported(cls, v):
        return _coerce_str_list(v)

    @field_validator("total_claims", mode="before")
    @classmethod
    def _v_total(cls, v):
        return _coerce_int(v)


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
