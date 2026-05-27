"""子块文本服务。

负责把写入向量库的 child docs 同步镜像到 MySQL，
供 BM25 索引构建（不再走向量库的 list-all）。
"""
import uuid
from typing import Optional

from langchain_core.documents import Document
from sqlalchemy import select, delete, or_

from app.db.db_config import AsyncSessionLocal
from app.models.chat_history import ChildChunk
from app.core.logger_handler import logger


class ChildChunkService:

    async def save_batch(self, child_docs: list[Document]) -> list[str]:
        """批量保存子块；为每个 doc 生成 chunk_id 并回填到 metadata。

        ⚠️ 副作用：会原地修改 child_docs[i].metadata，注入 chunk_id key。
        调用方应在本函数返回后再把 child_docs 喂给向量库，
        让两边主键一致（删除时能对齐）。

        Returns: 生成的 chunk_id 列表，顺序与入参一致。
        """
        if not child_docs:
            return []
        chunk_ids: list[str] = []
        async with AsyncSessionLocal() as db:
            for doc in child_docs:
                meta = doc.metadata
                chunk_id = meta.get("chunk_id") or str(uuid.uuid4())
                meta["chunk_id"] = chunk_id
                chunk_ids.append(chunk_id)
                db.add(ChildChunk(
                    chunk_id=chunk_id,
                    user_id=meta.get("user_id", ""),
                    kb_id=meta.get("kb_id"),
                    file_id=meta.get("file_id", ""),
                    parent_id=meta.get("parent_id"),
                    filename=meta.get("filename"),
                    content=doc.page_content,
                    chunk_index=meta.get("chunk_index", 0),
                ))
            await db.commit()
        logger.info(f"[ChildChunk] 保存 {len(child_docs)} 个子块")
        return chunk_ids

    async def load_filtered(
        self,
        user_id: Optional[str] = None,
        kb_ids: Optional[list[str]] = None,
    ) -> list[Document]:
        """按用户 / 知识库范围拉子块。

        过滤逻辑与 _build_rag_filter 保持一致：
        - 给了 user_id + kb_ids：user_id 自有 OR kb_id ∈ kb_ids
        - 只给了 user_id：仅 user_id 自有
        - 都没给：全部（仅供管理 / 调试）
        """
        async with AsyncSessionLocal() as db:
            stmt = select(ChildChunk)
            if user_id and kb_ids:
                stmt = stmt.where(or_(
                    ChildChunk.user_id == user_id,
                    ChildChunk.kb_id.in_(kb_ids),
                ))
            elif user_id:
                stmt = stmt.where(ChildChunk.user_id == user_id)
            result = await db.execute(stmt)
            rows = result.scalars().all()
        return [
            Document(
                page_content=row.content,
                metadata={
                    "chunk_id": row.chunk_id,
                    "file_id": row.file_id,
                    "user_id": row.user_id,
                    "kb_id": row.kb_id,
                    "parent_id": row.parent_id,
                    "filename": row.filename,
                    "chunk_index": row.chunk_index,
                },
            )
            for row in rows
        ]

    async def delete_by_doc_id(self, doc_id: str) -> list[str]:
        """按 doc_id 删除子块，返回被删除的 chunk_id 列表（供向量库同步删）。

        doc_id 在子块表里以 file_id 字段存（与向量库 metadata key 对齐）。
        """
        async with AsyncSessionLocal() as db:
            stmt = select(ChildChunk.chunk_id).where(ChildChunk.file_id == doc_id)
            result = await db.execute(stmt)
            chunk_ids = [row[0] for row in result.all()]
            await db.execute(delete(ChildChunk).where(ChildChunk.file_id == doc_id))
            await db.commit()
        logger.info(f"[ChildChunk] 删除 doc_id={doc_id} 共 {len(chunk_ids)} 个子块")
        return chunk_ids

    async def delete_by_user(self, user_id: str) -> list[str]:
        async with AsyncSessionLocal() as db:
            stmt = select(ChildChunk.chunk_id).where(ChildChunk.user_id == user_id)
            result = await db.execute(stmt)
            chunk_ids = [row[0] for row in result.all()]
            await db.execute(delete(ChildChunk).where(ChildChunk.user_id == user_id))
            await db.commit()
        logger.info(f"[ChildChunk] 清空 user_id={user_id} 共 {len(chunk_ids)} 个子块")
        return chunk_ids


child_chunk_service = ChildChunkService()
