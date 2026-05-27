"""向量存储后端抽象层。

通过 VECTOR_STORE_BACKEND 环境变量选择 chroma 或 milvus。
业务层只与 VectorStoreBackend 协议交互。
"""
from app.rag.vector_backend.base import VectorStoreBackend
from app.rag.vector_backend.factory import build_backend

__all__ = ["VectorStoreBackend", "build_backend"]
