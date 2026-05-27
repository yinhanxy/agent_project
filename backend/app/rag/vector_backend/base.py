"""向量存储后端协议。

实现者：ChromaBackend / MilvusBackend
业务层契约：所有 filter 用 Chroma 风格的 dict（$or/$and/$eq/$in），
backend 内部负责转译为各自原生格式。
"""
from typing import Protocol, runtime_checkable, Optional

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever


@runtime_checkable
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
        filter_meta: Optional[dict] = None,
    ) -> BaseRetriever:
        """返回一个相似度检索器；filter_meta 用 dict 形式。"""
        ...

    async def delete_by_filter(self, filter_meta: dict) -> None:
        """按 metadata 条件删除（如 {"file_id": "xxx"} 或 {"user_id": "yyy"}）。"""
        ...
