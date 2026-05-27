"""Milvus 后端实现。

依赖 langchain-milvus 提供的 Milvus 向量库封装。
filter 通过 milvus_filter.dict_to_milvus_expr 转译。
删除：用 pymilvus 原生 col.delete(expr=...)，因为 langchain-milvus 的 delete 仅支持 ids。
"""
import asyncio

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_milvus import Milvus

from app.rag.vector_backend.base import VectorStoreBackend
from app.rag.vector_backend.milvus_filter import dict_to_milvus_expr
from app.utils.config import milvus_config
from app.utils.factory import embed_model
from app.core.logger_handler import logger


class MilvusBackend(VectorStoreBackend):
    def __init__(self) -> None:
        connection_args = {
            "host": milvus_config["host"],
            "port": str(milvus_config["port"]),
        }
        self._store = Milvus(
            embedding_function=embed_model,
            collection_name=milvus_config["collection_name"],
            connection_args=connection_args,
            auto_id=True,
            # 启用 dynamic field，元数据 schema 不固定，避免后续加字段要 alter
            enable_dynamic_field=True,
            index_params={
                "metric_type": "L2",
                "index_type": "AUTOINDEX",
                "params": {},
            },
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
        expr = dict_to_milvus_expr(filter_meta)
        if expr:
            # langchain-milvus 的 expr key 名称就是 "expr"
            search_kwargs["expr"] = expr
        return self._store.as_retriever(
            search_type="similarity",
            search_kwargs=search_kwargs,
        )

    async def delete_by_filter(self, filter_meta: dict) -> None:
        """走 pymilvus col.delete(expr=...)。

        契约：filter_meta 不能为空（与 base.py Protocol 一致），
        否则 dict_to_milvus_expr 返回空字符串，会被这里拒绝。
        """
        if not filter_meta:
            raise ValueError(
                "delete_by_filter 不接受空 filter_meta，会导致全量删除"
            )
        expr = dict_to_milvus_expr(filter_meta)
        if not expr:
            raise ValueError(
                f"filter_meta={filter_meta!r} 转译后表达式为空，拒绝执行删除"
            )

        def _do_delete() -> None:
            col = self._store.col  # pymilvus Collection
            if col is None:
                logger.warning("[MilvusBackend] 集合尚未创建，跳过删除")
                return
            col.delete(expr=expr)
            col.flush()

        await asyncio.to_thread(_do_delete)
        logger.info(f"[MilvusBackend] 已删除 expr={expr}")
