from eval.threshold_sweep import sweep, best_threshold


def test_sweep_computes_pr_f1_per_threshold():
    # (max_score, expect_gap)：低分应触发缺口
    pairs = [(0.9, False), (0.85, False), (0.4, True), (0.3, True)]
    rows = sweep(pairs, thresholds=[0.5, 0.8])
    # 阈值 0.5：predicted_gap = score<0.5 → 后两条触发，完美 → P=R=F1=1
    assert rows[0.5]["precision"] == 1.0 and rows[0.5]["recall"] == 1.0
    # 阈值 0.8：0.4/0.3 触发(对) + 无误触发 → 仍完美；0.85/0.9 不触发(对)
    assert rows[0.8]["recall"] == 1.0


def test_best_threshold_picks_max_f1():
    rows = {0.5: {"f1": 0.8}, 0.7: {"f1": 0.95}, 0.9: {"f1": 0.6}}
    assert best_threshold(rows) == 0.7
