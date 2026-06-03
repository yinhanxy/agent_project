"""申请/说明文本任务：构造让 LLM 生成规范申请文本的 prompt。"""

_SYSTEM = (
    "你是企业知识库申请/说明文本助手。基于公司制度文档，为用户生成规范的申请或说明文本，"
    "内容须符合制度要求、措辞正式。\n"
    "只基于给定文档中的制度依据，不得编造制度细节；若关键制度缺失，请提示用户补充。"
)


def _format_context(documents: list[str]) -> str:
    if not documents:
        return "（未检索到相关文档）"
    return "\n\n".join(f"【文档片段{i}】\n{d}" for i, d in enumerate(documents, 1))


def build_messages(query: str, documents: list[str]) -> list[dict]:
    user = (
        f"请基于以下制度文档片段，生成符合制度要求的申请/说明文本。\n\n"
        f"{_format_context(documents)}\n\n用户需求：{query}"
    )
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user},
    ]
