"""ChromaDB 后端实现。

把原 vector_store.py 里的 Chroma 调用搬到这里，
保持嵌入式持久化目录 + dict filter 的现有行为。
"""
import asyncio

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from app.rag.vector_backend.base import VectorStoreBackend
from app.utils.config import chroma_config
from app.utils.factory import embed_model
from app.utils.path_tool import get_abstract_path


class ChromaBackend(VectorStoreBackend):
    def __init__(self) -> None:
        persist_dir = get_abstract_path(chroma_config["persist_directory"])
        self._store = Chroma(
            collection_name=chroma_config["collection_name"],
            embedding_function=embed_model,
            persist_directory=persist_dir,
        )

    async def add_documents(self, docs: list[Document]) -> None:
        if not docs:
            return
        await asyncio.to_thread(self._store.add_documents, docs)

    async def as_retriever(
        self,
        k: int,
        filter_meta: dict | None = None,
    ) -> BaseRetriever:
        search_kwargs: dict = {"k": k}
        if filter_meta:
            search_kwargs["filter"] = filter_meta
        return self._store.as_retriever(
            search_type="similarity",
            search_kwargs=search_kwargs,
        )

    async def delete_by_filter(self, filter_meta: dict) -> None:
        if not filter_meta:
            return
        await asyncio.to_thread(self._store.delete, where=filter_meta)
