"""知识缺口 service：落库（去重）/ 查询（按身份过滤）/ 改状态（越权防护）。仿 document_service。"""
import datetime
from typing import List, Dict, Any, Optional

from app.db.db_config import AsyncSessionLocal
from app.models.chat_history import KnowledgeGap
from app.core.logger_handler import logger

_VALID_STATUS = {"pending", "reviewed", "resolved", "ignored"}


class KnowledgeGapService:

    async def save_gap(
        self, user_id: str, dept_id: Optional[str], title: str,
        question: str, category: str, suggested_content: str,
    ) -> None:
        """去重：同 user_id + 相同 question + status='pending' 已存在则 touch updated_at；否则插入。"""
        async with AsyncSessionLocal() as db:
            existing = await db.run_sync(
                lambda s: s.query(KnowledgeGap)
                .filter(
                    KnowledgeGap.user_id == user_id,
                    KnowledgeGap.question == question,
                    KnowledgeGap.status == "pending",
                )
                .first()
            )
            if existing:
                existing.updated_at = datetime.datetime.now(datetime.timezone.utc)
                await db.commit()
                logger.info(f"[GapService] 去重命中，touch gap id={existing.id} user={user_id}")
                return
            gap = KnowledgeGap(
                user_id=user_id, dept_id=dept_id, title=title,
                question=question, category=category, suggested_content=suggested_content,
            )
            db.add(gap)
            await db.commit()
            logger.info(f"[GapService] 新增缺口 user={user_id} title={title}")

    async def list_gaps(
        self, user_id: str, is_admin: bool, status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        async with AsyncSessionLocal() as db:
            def _query(s):
                q = s.query(KnowledgeGap)
                if not is_admin:
                    q = q.filter(KnowledgeGap.user_id == user_id)
                if status:
                    q = q.filter(KnowledgeGap.status == status)
                return q.order_by(KnowledgeGap.updated_at.desc()).all()
            records = await db.run_sync(_query)
            return [self._to_dict(r) for r in records]

    async def update_status(
        self, gap_id: int, user_id: str, is_admin: bool, status: str
    ) -> bool:
        if status not in _VALID_STATUS:
            raise ValueError(f"非法状态: {status}")
        async with AsyncSessionLocal() as db:
            gap = await db.run_sync(
                lambda s: s.query(KnowledgeGap).filter(KnowledgeGap.id == gap_id).first()
            )
            if not gap:
                return False
            if not is_admin and gap.user_id != user_id:
                raise PermissionError("无权修改他人的知识缺口")
            gap.status = status
            await db.commit()
            return True

    @staticmethod
    def _to_dict(r: KnowledgeGap) -> Dict[str, Any]:
        return {
            "id": r.id,
            "user_id": r.user_id,
            "title": r.title,
            "question": r.question,
            "category": r.category,
            "suggested_content": r.suggested_content,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }


knowledge_gap_service = KnowledgeGapService()
