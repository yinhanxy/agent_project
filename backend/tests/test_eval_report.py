from eval.report import render_summary, render_cost


def _ms(mean, std):
    return {"mean": mean, "std": std}


def test_summary_has_orchestration_columns_and_meanstd():
    matrix = {
        "baseline": {"n": 20, "repeat": 2,
                     "recall@1": _ms(1.0, 0.0),
                     "recall@3": _ms(0.9, 0.0), "mrr": _ms(0.85, 0.02),
                     "assert_pass_rate": _ms(0.8, 0.1),
                     "route_accuracy": _ms(0.95, 0.0),
                     "gap_precision": _ms(1.0, 0.0), "gap_recall": _ms(0.75, 0.0)},
        "+critic": {"n": 20, "repeat": 2,
                    "recall@1": _ms(1.0, 0.0),
                    "recall@3": _ms(0.9, 0.0), "mrr": _ms(0.9, 0.0),
                    "assert_pass_rate": _ms(0.95, 0.05),
                    "route_accuracy": _ms(0.95, 0.0),
                    "gap_precision": _ms(1.0, 0.0), "gap_recall": _ms(1.0, 0.0)},
    }
    md = render_summary(matrix)
    assert "路由准确率" in md
    assert "缺口" in md
    assert "recall@1" in md
    assert "0.900±0.000" in md       # mean±std 格式
    assert "baseline" in md and "+critic" in md


def test_cost_table_meanstd():
    cost = {"baseline": {"avg_tokens": _ms(1200.0, 50.0), "avg_latency_s": _ms(3.4, 0.2)}}
    md = render_cost(cost)
    assert "1200.000±50.000" in md or "1200.0" in md
