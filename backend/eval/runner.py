r"""评估编排：父进程逐配置起子进程，子进程跑全量数据集，父进程聚合出报告。

用法（backend 目录，需 seed_corpus 已灌库、真实模型在跑）：
    .\.venv\Scripts\python.exe -m eval.runner
"""
import argparse
import asyncio
import json
import os
import statistics
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from eval.config import CONFIG_MATRIX
from eval.judge_model import build_judge_model
from eval.judges.assertion_judge import check_assertions
from eval.judges.grounding_judge import judge_faithfulness
from eval.judges.llm_judge import judge_coverage
from eval.metrics import recall_at_k, mrr, aggregate, route_accuracy, gap_precision_recall
from eval.report import render_summary, render_cost
from eval.schema import load_cases

EVAL_DIR = Path(__file__).resolve().parent
DATASET = EVAL_DIR / "datasets" / "retrieval.jsonl"
ROUTING = EVAL_DIR / "datasets" / "routing.jsonl"
TASKS = EVAL_DIR / "datasets" / "tasks.jsonl"
REPORTS = EVAL_DIR / "reports"
EVAL_REPEAT = int(os.getenv("EVAL_REPEAT", "2"))


def _mean_std(values: list) -> dict:
    vals = [v for v in values if v is not None]
    if not vals:
        return {"mean": None, "std": None}
    return {"mean": sum(vals) / len(vals),
            "std": statistics.pstdev(vals) if len(vals) > 1 else 0.0}


def _score_single(cases: list, raw: list) -> tuple:
    """单次运行的原始结果 -> (指标 dict, 成本 dict)。"""
    by_id = {r["id"]: r for r in raw}
    per_case = []
    route_pairs = []
    gap_pairs = []
    for c in cases:
        r = by_id.get(c.id, {})
        ranked = r.get("ranked_filenames", [])
        per_case.append({
            "recall@1": recall_at_k(ranked, c.expected_doc, k=1),
            "recall@3": recall_at_k(ranked, c.expected_doc, k=3),
            "mrr": mrr(ranked, c.expected_doc),
            "assert_pass": check_assertions(r.get("answer", ""), c.answer_assertions),
        })
        route_pairs.append((r.get("route"), c.expected_route))
        gap_pairs.append((r.get("gap_triggered", False), c.expect_gap_triggered))
    metrics = aggregate(per_case)
    metrics["route_accuracy"] = route_accuracy(route_pairs)
    gp, gr = gap_precision_recall(gap_pairs)
    metrics["gap_precision"] = gp
    metrics["gap_recall"] = gr
    covs = [r.get("coverage") for r in raw if r.get("coverage") is not None]
    faiths = [r.get("faithfulness") for r in raw if r.get("faithfulness") is not None]
    metrics["coverage"] = statistics.fmean(covs) if covs else None
    metrics["faithfulness"] = statistics.fmean(faiths) if faiths else None
    toks = [r.get("tokens", 0) for r in raw] or [0]
    lats = [r.get("latency_s", 0.0) for r in raw] or [0.0]
    cost = {"avg_tokens": sum(toks) / len(toks), "avg_latency_s": sum(lats) / len(lats)}
    return metrics, cost


def score_runs(cases: list, runs: list) -> tuple:
    """多次运行 -> 每个指标 mean/std。runs: list[raw_results]。"""
    scored = [_score_single(cases, raw) for raw in runs]
    metric_keys = ["recall@1", "recall@3", "mrr", "assert_pass_rate",
                   "route_accuracy", "gap_precision", "gap_recall", "coverage", "faithfulness"]
    cost_keys = sorted({k for _, c in scored for k in c.keys()})
    metrics = {k: _mean_std([m.get(k) for m, _ in scored]) for k in metric_keys}
    metrics["n"] = scored[0][0].get("n", 0) if scored else 0
    metrics["repeat"] = len(runs)
    cost = {k: _mean_std([c.get(k) for _, c in scored]) for k in cost_keys}
    return metrics, cost


async def judge_open_tasks(cases: list, raw: list) -> None:
    """就地给 raw 里属于开放式任务（有 rubric_points）的题补 coverage / faithfulness。"""
    by_id = {c.id: c for c in cases}
    model = build_judge_model()
    for r in raw:
        c = by_id.get(r["id"])
        if not c or not c.rubric_points:
            continue
        r["coverage"] = await judge_coverage(model, c.question, r.get("answer", ""), c.rubric_points)
        r["faithfulness"] = await judge_faithfulness(model, r.get("answer", ""), r.get("doc_previews", []))


async def _worker(out_path: str):
    """子进程：按当前 env 编译被测系统，跑全量数据集，写 json。"""
    from eval.system_under_test import run_dataset
    cases = load_cases(DATASET) + load_cases(ROUTING) + load_cases(TASKS)
    raw = await run_dataset(cases)
    await judge_open_tasks(cases, raw)
    Path(out_path).write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")


def _run_config_subprocess(cfg, tmp_dir: Path) -> list:
    """父进程：起注入 env 的子进程多次跑某配置，读回多次原始结果。"""
    env = {**os.environ, **cfg.env}
    runs = []
    for i in range(EVAL_REPEAT):
        out_path = tmp_dir / f"{cfg.name}.run{i}.json"
        proc = subprocess.run(
            [sys.executable, "-m", "eval.runner", "--worker", "--out", str(out_path)],
            env=env, cwd=str(EVAL_DIR.parent),   # cwd=backend
        )
        if proc.returncode != 0:
            raise RuntimeError(f"配置 {cfg.name} 第{i}次子进程失败，returncode={proc.returncode}")
        runs.append(json.loads(out_path.read_text(encoding="utf-8")))
    return runs


def main():
    cases = load_cases(DATASET) + load_cases(ROUTING) + load_cases(TASKS)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = REPORTS / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    metrics_matrix, cost_matrix, details = {}, {}, {}
    for cfg in CONFIG_MATRIX:
        print(f"[runner] 跑配置 {cfg.name} ×{EVAL_REPEAT} env={cfg.env}")
        runs = _run_config_subprocess(cfg, out_dir)
        metrics, cost = score_runs(cases, runs)
        metrics_matrix[cfg.name] = metrics
        cost_matrix[cfg.name] = cost
        details[cfg.name] = runs

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
