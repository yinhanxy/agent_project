"""向量存储后端协议。

实现者：ChromaBackend / MilvusBackend
业务层契约：所有 filter 用 Chroma 风格的 dict（支持 $or / $and / $eq / $ne / $in / $nin），
backend 内部负责转译为各自原生格式。
"""
from typing import Protocol

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever


class VectorStoreBackend(Protocol):
    """向量库后端协议（add / retriever / delete）。

    不在协议里暴露 `get_all_documents`，BM25 索引数据另起 MySQL 子块表。
    """

    async def add_documents(self, docs: list[Document]) -> None:
        """批量写入子块（含 metadata.file_id / user_id / kb_id 等）。"""
        ...

    async def as_retriever(
        self,
        k: int,
        filter_meta: dict | None = None,
    ) -> BaseRetriever:
        """返回一个相似度检索器；filter_meta 用 Chroma 风格 dict。"""
        ...

    async def delete_by_filter(self, filter_meta: dict) -> None:
        """按 metadata 条件删除。

        支持 Chroma 风格 dict（含 $or / $and / $eq / $in 等），
        如 {"file_id": "xxx"} 或 {"user_id": "yyy"} 或
        {"$or": [{"user_id": "u1"}, {"kb_id": {"$in": ["a","b"]}}]}。

        契约：filter_meta 不能为空或 None，实现应 raise ValueError，
        避免误删整张集合（Chroma where={} 会全删，是危险行为）。
        """
        ...
