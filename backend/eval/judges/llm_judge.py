"""LLM-judge：开放式输出按 rubric_points 逐点核对覆盖率。逐点核对而非整体打分，降 judge 波动。"""
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


class CoverageVerdict(BaseModel):
    covered_points: list[str] = []   # 回答确实覆盖到的 rubric 要点（原样回填）
    reasoning: str = ""

    @field_validator("covered_points", mode="before")
    @classmethod
    def _v_covered(cls, v):
        return _coerce_str_list(v)


def coverage_ratio(covered_points: list, total: int) -> Optional[float]:
    """覆盖率 = 覆盖点数 / rubric 总点数。total=0（无 rubric）返回 None。"""
    if not total:
        return None
    return len(covered_points or []) / total


_SYSTEM = (
    "你是严格的评审。给定一个问题、一段回答、和一组评分要点(rubric)。"
    "逐条判断回答是否实质覆盖了每个要点，只把确实覆盖到的要点原样列入 covered_points。"
    "不要臆测、不要把未覆盖的算作覆盖。"
)


async def judge_coverage(model, question: str, answer: str, rubric_points: list) -> Optional[float]:
    """用 judge 模型核对覆盖率。model 由调用方注入（生产用 build_judge_model()）。"""
    if not rubric_points:
        return None
    user = (f"问题：{question}\n\n回答：{answer}\n\n"
            f"评分要点：\n" + "\n".join(f"- {p}" for p in rubric_points))
    structured = model.with_structured_output(CoverageVerdict)
    verdict = await structured.ainvoke(
        [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}])
    # 只统计确实属于 rubric 的覆盖点（防 judge 编造点）
    covered = [p for p in verdict.covered_points if p in rubric_points]
    return coverage_ratio(covered, total=len(rubric_points))
