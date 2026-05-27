"""
父块存储服务。

父子检索中，ChromaDB 存小的 child chunk（精准向量检索），
MySQL 存大的 parent chunk（给 LLM 完整上下文）。
检索链路：child 命中 → 读 parent_id → 从这里取父块内容。
"""
from typing import List, Dict

from app.db.db_config import AsyncSessionLocal
from app.models.chat_history import ParentChunk
from app.core.logger_handler import logger


class ParentChunkService:

    async def save_batch(self, parent_docs: list) -> None:
        """批量保存父块；每个 doc 需有 metadata.parent_id / doc_id / user_id"""
        if not parent_docs:
            return
        async with AsyncSessionLocal() as db:
            for doc in parent_docs:
                meta = doc.metadata
                record = ParentChunk(
                    parent_id=meta["parent_id"],
                    doc_id=meta.get("doc_id", ""),
                    user_id=meta.get("user_id", ""),
                    content=doc.page_content,
                    chunk_index=meta.get("chunk_index", 0),
                )
                db.add(record)
            await db.commit()
        logger.info(f"[ParentChunk] 保存 {len(parent_docs)} 个父块")

    async def get_by_ids(self, parent_ids: List[str]) -> Dict[str, str]:
        """批量查询，返回 {parent_id: content}"""
        if not parent_ids:
            return {}
        async with AsyncSessionLocal() as db:
            records = await db.run_sync(
                lambda s: s.query(ParentChunk)
                .filter(ParentChunk.parent_id.in_(parent_ids))
                .all()
            )
        return {r.parent_id: r.content for r in records}

    async def delete_by_doc_id(self, doc_id: str) -> None:
        async with AsyncSessionLocal() as db:
            records = await db.run_sync(
                lambda s: s.query(ParentChunk)
                .filter(ParentChunk.doc_id == doc_id)
                .all()
            )
            for r in records:
                await db.delete(r)
            await db.commit()
        logger.info(f"[ParentChunk] 删除 doc_id={doc_id} 的全部父块")

    async def delete_by_user(self, user_id: str) -> None:
        async with AsyncSessionLocal() as db:
            records = await db.run_sync(
                lambda s: s.query(ParentChunk)
                .filter(ParentChunk.user_id == user_id)
                .all()
            )
            for r in records:
                await db.delete(r)
            await db.commit()
        logger.info(f"[ParentChunk] 删除 user_id={user_id} 的全部父块")


parent_chunk_service = ParentChunkService()
