"""LLM-judge：开放式输出按 rubric_points 逐点核对覆盖率。逐点核对而非整体打分，降 judge 波动。"""
from typing import Optional
from pydantic import BaseModel


class CoverageVerdict(BaseModel):
    covered_points: list[str]   # 回答确实覆盖到的 rubric 要点（原样回填）
    reasoning: str


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
