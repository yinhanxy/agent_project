"""数据集质量红线：数量、字段完整性、语料引用一致性、id 唯一。

这是数据集扩充（Task 2~5）的验收门。codex 扩到达标后本测试全绿。
直接读 jsonl raw（不经 load_cases），以便校验 expected_docs 等字段。
"""
import json
from pathlib import Path

EVAL = Path(__file__).resolve().parent.parent / "eval" / "datasets"
CORPUS = Path(__file__).resolve().parents[2] / "docs" / "test-corpus"

RETRIEVAL = EVAL / "retrieval.jsonl"
ROUTING = EVAL / "routing.jsonl"
TASKS = EVAL / "tasks.jsonl"

ROUTE_TYPES = {
    "knowledge_qa",
    "document_compare",
    "report_generation",
    "document_generation",
    "knowledge_gap",
}
TASK_TYPES = {"document_compare", "report_generation", "document_generation"}


def _load(path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _corpus_files():
    return {p.name for p in CORPUS.glob("*.md") if p.name != "README.md"}


def test_corpus_has_at_least_10_docs():
    assert len(_corpus_files()) >= 10, "语料需 ≥10 篇，让 recall@k 有区分度"


def test_retrieval_size_and_fields():
    rows = _load(RETRIEVAL)
    assert len(rows) >= 40, f"retrieval 需 ≥40 条，当前 {len(rows)}"
    files = _corpus_files()
    refuse = 0
    for r in rows:
        assert r["id"] and r["question"] and r["type"]
        if r.get("should_refuse"):
            refuse += 1
            continue
        # 非拒答题：expected_doc 必须指向真实语料文件，且有事实断言
        assert r.get("expected_doc") in files, (
            f"{r['id']} expected_doc 不在语料：{r.get('expected_doc')}"
        )
        ai = r.get("answer_assertions") or {}
        assert ai.get("must_include"), f"{r['id']} 非拒答题须有 must_include 断言"
    assert refuse >= 6, f"拒答负样本需 ≥6，当前 {refuse}"


def test_tasks_size_and_type_balance():
    rows = _load(TASKS)
    assert len(rows) >= 21, f"tasks 需 ≥21 条（解 n=4 炸点），当前 {len(rows)}"
    files = _corpus_files()
    by_type = {t: 0 for t in TASK_TYPES}
    for r in rows:
        assert r["type"] in TASK_TYPES, f"{r['id']} type 非法：{r['type']}"
        by_type[r["type"]] += 1
        pts = r.get("rubric_points") or []
        assert len(pts) >= 3, f"{r['id']} rubric_points 需 ≥3 点"
        for d in r.get("expected_docs") or []:
            assert d in files, f"{r['id']} expected_docs 不在语料：{d}"
    for t, n in by_type.items():
        assert n >= 7, f"开放式类型 {t} 需 ≥7 条，当前 {n}"


def test_routing_size_and_gap_balance():
    rows = _load(ROUTING)
    assert len(rows) >= 32, f"routing 需 ≥32 条，当前 {len(rows)}"
    gap = 0
    for r in rows:
        assert r["expected_route"] in ROUTE_TYPES, (
            f"{r['id']} route 非法：{r['expected_route']}"
        )
        if r["expected_route"] == "knowledge_gap":
            gap += 1
            assert r.get("expect_gap_triggered") is True, (
                f"{r['id']} gap 题须 expect_gap_triggered=true"
            )
    assert gap >= 8, f"knowledge_gap 负样本需 ≥8（缺口指标分母），当前 {gap}"


def test_ids_globally_unique():
    all_ids = [
        r["id"] for path in (RETRIEVAL, ROUTING, TASKS) for r in _load(path)
    ]
    dup = {i for i in all_ids if all_ids.count(i) > 1}
    assert not dup, f"存在重复 id：{dup}"
