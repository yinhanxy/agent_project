"""文档对比任务：构造让 LLM 输出对比表格的 prompt。"""

_SYSTEM = (
    "你是企业知识库文档对比助手。基于提供的文档片段，对用户关心的对象"
    "（如新旧版制度）进行对比，输出 Markdown 表格。\n"
    "表格列建议：| 对比项 | 旧版/对象A | 新版/对象B | 影响 |。\n"
    "只基于给定文档，不得编造制度内容；若文档不足以对比，请明确说明知识库信息不足。"
)


def _format_context(documents: list[str]) -> str:
    if not documents:
        return "（未检索到相关文档）"
    return "\n\n".join(f"【文档片段{i}】\n{d}" for i, d in enumerate(documents, 1))


def build_messages(query: str, documents: list[str]) -> list[dict]:
    user = (
        f"请基于以下文档片段进行对比，并输出 Markdown 表格。\n\n"
        f"{_format_context(documents)}\n\n用户需求：{query}"
    )
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user},
    ]
