"""后端工厂：按环境变量决定实例化哪个 backend。"""
import os

from app.rag.vector_backend.base import VectorStoreBackend
from app.core.logger_handler import logger


def build_backend() -> VectorStoreBackend:
    backend_type = os.getenv("VECTOR_STORE_BACKEND", "chroma").lower()
    if backend_type == "milvus":
        from app.rag.vector_backend.milvus_backend import MilvusBackend
        logger.info("[VectorBackend] 使用 MilvusBackend")
        return MilvusBackend()
    if backend_type == "chroma":
        from app.rag.vector_backend.chroma_backend import ChromaBackend
        logger.info("[VectorBackend] 使用 ChromaBackend")
        return ChromaBackend()
    raise ValueError(
        f"未知的 VECTOR_STORE_BACKEND={backend_type!r}，"
        f"可选: chroma | milvus"
    )
