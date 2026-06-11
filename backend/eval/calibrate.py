"""LLM-judge 人工校准：算 judge 与人工标注的一致率，证明 judge 可信。

人工标注放 backend/eval/datasets/calibration.jsonl，每行：
  {"id": "cmp-001", "human_coverage": 0.8}
用法：先跑一次 eval.runner 拿 judge 分，再人工标 10 条，跑本脚本算 agreement。
"""
from typing import Optional


def agreement(pairs: list, tol: float = 0.25) -> Optional[float]:
    """pairs: [(judge_score, human_score)]；两者差 ≤ tol 视为一致。返回一致率。"""
    judged = [(j, h) for j, h in pairs if j is not None and h is not None]
    if not judged:
        return None
    return sum(1 for j, h in judged if abs(j - h) <= tol) / len(judged)
