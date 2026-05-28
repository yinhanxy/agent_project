"""Milvus 后端实现。

依赖 langchain-milvus 提供的 Milvus 向量库封装。
filter 通过 milvus_filter.dict_to_milvus_expr 转译。
删除：走 langchain-milvus 的 Milvus.delete(expr=...)，比 pymilvus ORM col.delete 更稳定。
"""
import asyncio

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_milvus import Milvus
from pymilvus import connections

from app.rag.vector_backend.base import VectorStoreBackend
from app.rag.vector_backend.milvus_filter import dict_to_milvus_expr
from app.utils.config import milvus_config
from app.utils.factory import embed_model
from app.core.logger_handler import logger


class _ORMAwareMilvus(Milvus):
    """修复 langchain-milvus 0.3.x + pymilvus 2.6.x 的连接不兼容。

    pymilvus 2.6 的 MilvusClient 改用 ConnectionManager，不再把连接注册到
    ORM 的全局 connections 表；但 langchain-milvus 的 `col` property 仍用
    ORM `Collection(name, using=self.alias)`，于是 add/search 触发
    `ConnectionNotExistException: should create connection first`。

    这里覆盖 col：访问前确保 self.alias 对应的 ORM 连接已建立。
    self.alias 在父类 __init__ 里先于 _extract_fields 设置，所以构造期访问也安全。
    """

    def __init__(self, *args, orm_uri: str = "", **kwargs) -> None:
        self._orm_uri = orm_uri
        super().__init__(*args, **kwargs)

    @property
    def col(self):  # type: ignore[override]
        alias = getattr(self, "alias", None)
        if alias and getattr(self, "_orm_uri", ""):
            try:
                connections._fetch_handler(alias)
            except Exception:
                connections.connect(alias=alias, uri=self._orm_uri)
        return Milvus.col.fget(self)


class MilvusBackend(VectorStoreBackend):
    def __init__(self) -> None:
        host = milvus_config["host"]
        port = milvus_config["port"]
        uri = f"http://{host}:{port}"
        self._store = _ORMAwareMilvus(
            embedding_function=embed_model,
            collection_name=milvus_config["collection_name"],
            connection_args={"uri": uri},
            orm_uri=uri,
            auto_id=True,
            # 启用 dynamic field，元数据 schema 不固定，避免后续加字段要 alter
            enable_dynamic_field=True,
            index_params={
                "metric_type": milvus_config.get("metric_type", "L2"),
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
            # 依赖 langchain-milvus 0.3.x：langchain_core.VectorStoreRetriever 把
            # search_kwargs 整体 unpack 给 Milvus.similarity_search(query, **kwargs)，
            # 后者的过滤参数名是 "expr"（不是 "filter"）。升级 langchain-* 后需重测。
            search_kwargs["expr"] = expr
        return self._store.as_retriever(
            search_type="similarity",
            search_kwargs=search_kwargs,
        )

    async def delete_by_filter(self, filter_meta: dict) -> None:
        """走 langchain-milvus 的 Milvus.delete(expr=...)。

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

        # langchain-milvus 0.3.x 的 Milvus.delete(expr=...) 内部走 MilvusClient.delete，
        # 比绕道 self._store.col (pymilvus 旧 ORM) 更稳定，且无需手动 flush。
        await asyncio.to_thread(self._store.delete, expr=expr)
        logger.info(f"[MilvusBackend] 已删除 expr={expr}")
