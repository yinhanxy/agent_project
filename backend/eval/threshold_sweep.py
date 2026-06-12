"""离线阈值扫描：用每题的 max_score 与缺口期望，对一组 RAG_GAP_THRESHOLD 算缺口 P/R/F1，
给阈值取值（尤其换 reranker 后）提供数据支撑。

用法（backend 目录，需评估环境）：
    .\\.venv\\Scripts\\python.exe -m eval.threshold_sweep
"""
import asyncio
from typing import Optional

from eval.metrics import gap_precision_recall
from eval.schema import load_cases
from eval.system_under_test import run_dataset
from eval.runner import ROUTING

_THRESHOLDS = [0.50, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]


def _f1(p: Optional[float], r: Optional[float]) -> Optional[float]:
    if not p or not r:
        return 0.0 if (p is not None and r is not None) else None
    return 2 * p * r / (p + r)


def sweep(pairs: list, thresholds: list) -> dict:
    """pairs: [(max_score, expect_gap)]。每个阈值算 predicted_gap=(ms is None or ms<t) 的 P/R/F1。"""
    rows = {}
    for t in thresholds:
        gap_pairs = [((ms is None or ms < t), eg) for ms, eg in pairs]
        p, r = gap_precision_recall(gap_pairs)
        rows[t] = {"precision": p, "recall": r, "f1": _f1(p, r)}
    return rows


def best_threshold(rows: dict) -> Optional[float]:
    """取 F1 最高的阈值。"""
    cand = [(t, v.get("f1")) for t, v in rows.items() if v.get("f1") is not None]
    return max(cand, key=lambda x: x[1])[0] if cand else None


def render(rows: dict) -> str:
    lines = ["# RAG_GAP_THRESHOLD 阈值扫描（缺口 P/R/F1）", "",
             "| 阈值 | 缺口精确率 | 缺口召回率 | F1 |", "|---|---|---|---|"]
    for t in sorted(rows):
        v = rows[t]
        def f(x): return "—" if x is None else f"{x:.3f}"
        lines.append(f"| {t:.2f} | {f(v['precision'])} | {f(v['recall'])} | {f(v['f1'])} |")
    bt = best_threshold(rows)
    lines += ["", f"> 推荐阈值（F1 最高）：**{bt:.2f}**。换 reranker 后据此更新 .env 的 RAG_GAP_THRESHOLD。"]
    return "\n".join(lines)


async def main():
    cases = load_cases(ROUTING)               # routing.jsonl 带 expect_gap_triggered
    raw = await run_dataset(cases)            # 当前 env（生产配置）跑一次，拿 max_score
    by_id = {r["id"]: r for r in raw}
    pairs = [(by_id.get(c.id, {}).get("max_score"), c.expect_gap_triggered) for c in cases]
    rows = sweep(pairs, _THRESHOLDS)
    print(render(rows))


if __name__ == "__main__":
    asyncio.run(main())
