def _ms(d) -> str:
    """格式化 {mean, std} 为 'mean±std'；None 给 —。"""
    if not isinstance(d, dict):
        return "—" if d is None else str(d)
    mean, std = d.get("mean"), d.get("std")
    if mean is None:
        return "—"
    return f"{mean:.3f}±{(std or 0.0):.3f}"


def render_summary(matrix: dict) -> str:
    lines = [
        "# 评估对比表（检索 + 回答 + 编排，mean±std）",
        "",
        "| 配置 | n | 重复 | recall@1 | recall@3 | MRR | 事实断言 | 路由准确率 | 缺口精确率 | 缺口召回率 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, m in matrix.items():
        lines.append(
            f"| {name} | {m.get('n','—')} | {m.get('repeat','—')} | "
            f"{_ms(m.get('recall@1'))} | {_ms(m.get('recall@3'))} | "
            f"{_ms(m.get('mrr'))} | {_ms(m.get('assert_pass_rate'))} | "
            f"{_ms(m.get('route_accuracy'))} | {_ms(m.get('gap_precision'))} | {_ms(m.get('gap_recall'))} |"
        )
    lines.append("")
    lines.append("> 样本量小（指示性，非统计显著）。mean±std 为同配置多次运行的均值与总体标准差；— 表示不适用。")
    return "\n".join(lines)


def render_cost(cost: dict) -> str:
    lines = [
        "# 成本对比表（延迟 / token，mean±std）",
        "",
        "| 配置 | 平均 token | 平均延迟秒 |",
        "|---|---|---|",
    ]
    for name, c in cost.items():
        lines.append(f"| {name} | {_ms(c.get('avg_tokens'))} | {_ms(c.get('avg_latency_s'))} |")
    return "\n".join(lines)
