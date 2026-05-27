"""
文档记录服务：替代原来的 MD5 文本文件，用 MySQL 管理文档元信息。

职责：
- 保存 / 查询 / 删除 document_records 表记录
- MD5 去重逻辑（改为按 user_id 隔离，修复跨用户误判 Bug）
- 为向量层提供文件名 → doc_id 的映射（支持替换语义）
"""
from typing import List, Optional, Dict, Any

from app.db.db_config import AsyncSessionLocal
from app.models.chat_history import DocumentRecord
from app.core.logger_handler import logger


class DocumentService:

    # ── 写操作 ────────────────────────────────────────────────────────────────

    async def save_record(
        self,
        doc_id: str,
        user_id: str,
        filename: str,
        md5_hex: str,
        file_size: int = 0,
        chunk_count: int = 0,
        kb_id: Optional[str] = None,
    ) -> None:
        async with AsyncSessionLocal() as db:
            record = DocumentRecord(
                doc_id=doc_id,
                user_id=user_id,
                kb_id=kb_id,
                filename=filename,
                md5_hex=md5_hex,
                file_size=file_size,
                chunk_count=chunk_count,
            )
            db.add(record)
            await db.commit()
            logger.info(f"[DocService] 保存记录 doc_id={doc_id} filename={filename} user={user_id} kb={kb_id}")

    async def delete_by_doc_id(self, doc_id: str, user_id: str) -> bool:
        """删除单条记录，返回是否找到并删除"""
        async with AsyncSessionLocal() as db:
            record = await db.run_sync(
                lambda s: s.query(DocumentRecord)
                .filter(DocumentRecord.doc_id == doc_id, DocumentRecord.user_id == user_id)
                .first()
            )
            if not record:
                return False
            await db.delete(record)
            await db.commit()
            logger.info(f"[DocService] 删除记录 doc_id={doc_id} user={user_id}")
            return True

    async def delete_by_user(self, user_id: str) -> int:
        """删除某用户的全部记录，返回删除条数"""
        async with AsyncSessionLocal() as db:
            records = await db.run_sync(
                lambda s: s.query(DocumentRecord)
                .filter(DocumentRecord.user_id == user_id)
                .all()
            )
            count = len(records)
            for r in records:
                await db.delete(r)
            await db.commit()
            logger.info(f"[DocService] 删除用户 {user_id} 全部 {count} 条记录")
            return count

    # ── 查询操作 ──────────────────────────────────────────────────────────────

    async def get_by_doc_id(self, doc_id: str, user_id: str) -> Optional[DocumentRecord]:
        async with AsyncSessionLocal() as db:
            return await db.run_sync(
                lambda s: s.query(DocumentRecord)
                .filter(DocumentRecord.doc_id == doc_id, DocumentRecord.user_id == user_id)
                .first()
            )

    async def get_by_filename(
        self, user_id: str, filename: str, kb_id: Optional[str] = None
    ) -> Optional[DocumentRecord]:
        """用于替换语义：上传同名文件时找到旧记录（按 kb_id 作用域隔离）"""
        async with AsyncSessionLocal() as db:
            kb_filter = (
                DocumentRecord.kb_id.is_(None)
                if kb_id is None
                else DocumentRecord.kb_id == kb_id
            )
            return await db.run_sync(
                lambda s: s.query(DocumentRecord)
                .filter(DocumentRecord.user_id == user_id, DocumentRecord.filename == filename, kb_filter)
                .first()
            )

    async def md5_exists(self, user_id: str, md5_hex: str, kb_id: Optional[str] = None) -> bool:
        """MD5 去重（按用户 + kb_id 作用域隔离）"""
        async with AsyncSessionLocal() as db:
            kb_filter = (
                DocumentRecord.kb_id.is_(None)
                if kb_id is None
                else DocumentRecord.kb_id == kb_id
            )
            record = await db.run_sync(
                lambda s: s.query(DocumentRecord)
                .filter(DocumentRecord.user_id == user_id, DocumentRecord.md5_hex == md5_hex, kb_filter)
                .first()
            )
            return record is not None

    async def list_by_user(self, user_id: str) -> List[Dict[str, Any]]:
        """返回用户个人文档列表（kb_id 为 NULL 的记录）"""
        async with AsyncSessionLocal() as db:
            records = await db.run_sync(
                lambda s: s.query(DocumentRecord)
                .filter(DocumentRecord.user_id == user_id, DocumentRecord.kb_id.is_(None))
                .order_by(DocumentRecord.upload_time.desc())
                .all()
            )
            return [self._record_to_dict(r) for r in records]

    async def list_by_kb(self, kb_id: str) -> List[Dict[str, Any]]:
        """返回指定知识库下的所有文档"""
        async with AsyncSessionLocal() as db:
            records = await db.run_sync(
                lambda s: s.query(DocumentRecord)
                .filter(DocumentRecord.kb_id == kb_id)
                .order_by(DocumentRecord.upload_time.desc())
                .all()
            )
            return [self._record_to_dict(r) for r in records]

    @staticmethod
    def _record_to_dict(r: DocumentRecord) -> Dict[str, Any]:
        return {
            "doc_id": r.doc_id,
            "filename": r.filename,
            "file_size": r.file_size,
            "chunk_count": r.chunk_count,
            "kb_id": r.kb_id,
            "upload_time": r.upload_time.isoformat() if r.upload_time else None,
        }


# 全局单例
document_service = DocumentService()
