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
