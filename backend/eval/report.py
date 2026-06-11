def _fmt(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def render_summary(matrix: dict) -> str:
    """matrix: {config_name: {n, recall@3, mrr, assert_pass_rate}} → markdown 对比表。"""
    lines = [
        "# 评估对比表（检索层 + 回答层事实断言）",
        "",
        "| 配置 | n | recall@3 | MRR | 事实断言通过率 |",
        "|---|---|---|---|---|",
    ]
    for name, m in matrix.items():
        lines.append(
            f"| {name} | {_fmt(m.get('n'))} | {_fmt(m.get('recall@3'))} | "
            f"{_fmt(m.get('mrr'))} | {_fmt(m.get('assert_pass_rate'))} |"
        )
    lines.append("")
    lines.append("> 样本量小（指示性，非统计显著）。None/— 表示该指标对该题不适用。")
    return "\n".join(lines)


def render_cost(cost: dict) -> str:
    """cost: {config_name: {avg_tokens, avg_latency_s}} → markdown 成本表。"""
    lines = [
        "# 成本对比表（延迟 / token）",
        "",
        "| 配置 | 平均 token (avg_tokens) | 平均延迟秒 (avg_latency_s) |",
        "|---|---|---|",
    ]
    for name, c in cost.items():
        lines.append(f"| {name} | {_fmt(c.get('avg_tokens'))} | {_fmt(c.get('avg_latency_s'))} |")
    return "\n".join(lines)
