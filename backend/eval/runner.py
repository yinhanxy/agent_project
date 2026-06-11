"""评估编排：父进程逐配置起子进程，子进程跑全量数据集，父进程聚合出报告。

用法（backend 目录，需 seed_corpus 已灌库、真实模型在跑）：
    .\.venv\Scripts\python.exe -m eval.runner
"""
import argparse
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from eval.config import CONFIG_MATRIX
from eval.judges.assertion_judge import check_assertions
from eval.metrics import recall_at_k, mrr, aggregate
from eval.report import render_summary, render_cost
from eval.schema import load_cases

EVAL_DIR = Path(__file__).resolve().parent
DATASET = EVAL_DIR / "datasets" / "retrieval.jsonl"
REPORTS = EVAL_DIR / "reports"


def score_results(cases: list, raw: list) -> tuple:
    """把子进程产出的每题原始结果，算成 (聚合指标 dict, 成本 dict)。"""
    by_id = {r["id"]: r for r in raw}
    per_case = []
    for c in cases:
        r = by_id.get(c.id, {})
        ranked = r.get("ranked_filenames", [])
        per_case.append({
            "recall@3": recall_at_k(ranked, c.expected_doc, k=3),
            "mrr": mrr(ranked, c.expected_doc),
            "assert_pass": check_assertions(r.get("answer", ""), c.answer_assertions),
        })
    metrics = aggregate(per_case)
    toks = [r.get("tokens", 0) for r in raw] or [0]
    lats = [r.get("latency_s", 0.0) for r in raw] or [0.0]
    cost = {"avg_tokens": sum(toks) / len(toks), "avg_latency_s": sum(lats) / len(lats)}
    return metrics, cost


async def _worker(out_path: str):
    """子进程：按当前 env 编译被测系统，跑全量数据集，写 json。"""
    from eval.system_under_test import run_dataset
    cases = load_cases(DATASET)
    raw = await run_dataset(cases)
    Path(out_path).write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")


def _run_config_subprocess(cfg, tmp_dir: Path) -> list:
    """父进程：起一个注入 env 的子进程跑某配置，读回原始结果。"""
    out_path = tmp_dir / f"{cfg.name}.json"
    env = {**os.environ, **cfg.env}
    proc = subprocess.run(
        [sys.executable, "-m", "eval.runner", "--worker", "--out", str(out_path)],
        env=env, cwd=str(EVAL_DIR.parent),   # cwd=backend
    )
    if proc.returncode != 0:
        raise RuntimeError(f"配置 {cfg.name} 子进程失败，returncode={proc.returncode}")
    return json.loads(out_path.read_text(encoding="utf-8"))


def main():
    cases = load_cases(DATASET)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = REPORTS / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    metrics_matrix, cost_matrix, details = {}, {}, {}
    for cfg in CONFIG_MATRIX:
        print(f"[runner] 跑配置 {cfg.name} env={cfg.env}")
        raw = _run_config_subprocess(cfg, out_dir)
        metrics, cost = score_results(cases, raw)
        metrics_matrix[cfg.name] = metrics
        cost_matrix[cfg.name] = cost
        details[cfg.name] = raw

    (out_dir / "summary.md").write_text(render_summary(metrics_matrix), encoding="utf-8")
    (out_dir / "cost.md").write_text(render_cost(cost_matrix), encoding="utf-8")
    (out_dir / "details.json").write_text(
        json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[runner] 完成。报告在 {out_dir}")
    print(render_summary(metrics_matrix))
    print(render_cost(cost_matrix))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", action="store_true", help="子进程模式：跑全量数据集吐 json")
    ap.add_argument("--out", help="worker 输出 json 路径")
    args = ap.parse_args()
    if args.worker:
        asyncio.run(_worker(args.out))
    else:
        main()
