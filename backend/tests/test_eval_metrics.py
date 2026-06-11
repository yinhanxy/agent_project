from eval.metrics import recall_at_k, mrr, aggregate


def test_recall_hit_within_k():
    assert recall_at_k(["a.md", "b.md", "c.md"], "b.md", k=3) == 1.0


def test_recall_miss_outside_k():
    assert recall_at_k(["a.md", "b.md", "c.md"], "b.md", k=1) == 0.0


def test_recall_no_expected_returns_none():
    # expected_doc 为 None（如纯拒答题）→ 该指标不适用
    assert recall_at_k(["a.md"], None, k=3) is None


def test_mrr_rank_two():
    assert mrr(["a.md", "b.md"], "b.md") == 0.5


def test_mrr_not_found():
    assert mrr(["a.md"], "z.md") == 0.0


def test_aggregate_means_ignore_none():
    per_case = [
        {"recall@3": 1.0, "mrr": 1.0, "assert_pass": True},
        {"recall@3": 0.0, "mrr": 0.0, "assert_pass": False},
        {"recall@3": None, "mrr": None, "assert_pass": True},   # 拒答题不计检索
    ]
    agg = aggregate(per_case)
    assert agg["recall@3"] == 0.5          # (1+0)/2，None 不计入
    assert agg["mrr"] == 0.5
    assert agg["assert_pass_rate"] == 2 / 3
    assert agg["n"] == 3


from eval.runner import score_results
from eval.schema import EvalCase


def test_score_results_combines_metrics_and_cost():
    cases = [
        EvalCase(id="qa-001", question="q1", type="knowledge_qa",
                 expected_doc="A.md", answer_assertions={"must_include": ["550"]}),
        EvalCase(id="qa-008", question="q2", type="knowledge_qa",
                 expected_doc=None, answer_assertions={}, should_refuse=True),
    ]
    raw = [
        {"id": "qa-001", "answer": "上限550元", "ranked_filenames": ["A.md", "B.md"],
         "tokens": 1000, "latency_s": 2.0, "trace_agents": []},
        {"id": "qa-008", "answer": "知识库没有依据", "ranked_filenames": ["X.md"],
         "tokens": 1400, "latency_s": 3.0, "trace_agents": []},
    ]
    metrics, cost = score_results(cases, raw)
    assert metrics["recall@3"] == 1.0          # 唯一有 expected 的题命中
    assert metrics["assert_pass_rate"] == 1.0  # 两题断言都过（qa-008 空断言=过）
    assert cost["avg_tokens"] == 1200.0
    assert cost["avg_latency_s"] == 2.5


def test_route_accuracy():
    from eval.metrics import route_accuracy
    pairs = [("knowledge_qa", "knowledge_qa"), ("document_compare", "knowledge_qa"),
             ("knowledge_gap", "knowledge_gap")]
    # (predicted, expected)
    assert route_accuracy(pairs) == 2 / 3


def test_route_accuracy_ignores_none_expected():
    from eval.metrics import route_accuracy
    assert route_accuracy([("knowledge_qa", None), ("a", "a")]) == 1.0  # 只算有 expected 的


def test_gap_precision_recall():
    from eval.metrics import gap_precision_recall
    # (predicted_triggered, expected_triggered)
    pairs = [(True, True), (True, False), (False, True), (False, False)]
    p, r = gap_precision_recall(pairs)
    assert p == 0.5   # TP=1, FP=1
    assert r == 0.5   # TP=1, FN=1


def test_gap_pr_no_expected_returns_none():
    from eval.metrics import gap_precision_recall
    p, r = gap_precision_recall([(False, None), (True, None)])
    assert p is None and r is None
