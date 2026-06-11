from eval.report import render_summary, render_cost


def test_summary_has_header_and_config_rows():
    matrix = {
        "baseline": {"n": 8, "recall@3": 0.75, "mrr": 0.62, "assert_pass_rate": 0.5},
        "+critic":  {"n": 8, "recall@3": 0.875, "mrr": 0.70, "assert_pass_rate": 0.625},
    }
    md = render_summary(matrix)
    assert "| 配置 |" in md
    assert "baseline" in md
    assert "+critic" in md
    assert "0.750" in md          # 数值格式化到 3 位
    assert "0.875" in md


def test_cost_table_renders_tokens_and_latency():
    cost = {
        "baseline": {"avg_tokens": 1200.0, "avg_latency_s": 3.4},
        "+hyde":    {"avg_tokens": 1800.0, "avg_latency_s": 5.1},
    }
    md = render_cost(cost)
    assert "avg_tokens" in md or "平均 token" in md
    assert "1200" in md
    assert "5.1" in md
