"""报告生成任务：构造让 LLM 输出结构化报告的 prompt。"""

_SYSTEM = (
    "你是企业知识库报告生成助手。基于提供的文档片段生成结构化 Markdown 报告，"
    "包含以下小节：## 背景、## 适用范围、## 核心流程、## 注意事项、## 风险点、## 参考文档。\n"
    "只基于给定文档，不得编造内容；若文档不足，请在相应小节注明信息缺失。"
)


def _format_context(documents: list[str]) -> str:
    if not documents:
        return "（未检索到相关文档）"
    return "\n\n".join(f"【文档片段{i}】\n{d}" for i, d in enumerate(documents, 1))


def build_messages(query: str, documents: list[str]) -> list[dict]:
    user = (
        f"请基于以下文档片段生成结构化报告。\n\n"
        f"{_format_context(documents)}\n\n报告主题：{query}"
    )
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user},
    ]
