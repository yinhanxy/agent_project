"""
知识库管理服务

支持三级知识库范围：
  personal  — 用户个人私有
  dept      — 部门共享（需 dept_id）
  company   — 全公司可见（任何人均可读）

权限等级（从低到高）：viewer < editor < admin
  - viewer : 只可检索
  - editor : 可上传 / 删除文档
  - admin  : 可管理成员、删除知识库
"""
import uuid
from typing import List, Optional, Dict, Any

from sqlalchemy.future import select
from sqlalchemy import or_, and_

from app.db.db_config import AsyncSessionLocal
from app.models.chat_history import KnowledgeBase, KBPermission, DocumentRecord
from app.core.logger_handler import logger

_ROLE_RANK = {"viewer": 0, "editor": 1, "admin": 2}


# ── 权限判定纯函数（无副作用，便于单元测试）──────────────────────────────────

def can_create_kb(
    scope: str,
    is_admin: bool,
    is_dept_admin: bool,
    user_dept_id: Optional[str],
    req_dept_id: Optional[str],
) -> tuple[bool, Optional[str]]:
    """判定能否创建某范围知识库，返回 (是否允许, 生效的 dept_id)。

    - personal：所有人
    - company / admin：仅总管理员
    - dept：总管理员可建任意部门库；部门管理员仅可建本部门库（未传 dept_id 则回填自身部门）
    """
    if scope == "personal":
        return True, None
    if scope in ("company", "admin"):
        return (True, None) if is_admin else (False, None)
    if scope == "dept":
        if is_admin:
            return True, (req_dept_id or None)
        if is_dept_admin and user_dept_id and req_dept_id in (None, "", user_dept_id):
            return True, user_dept_id
        return False, None
    return False, None


def assemble_rag_filter(
    user_id: str, is_admin: bool, accessible_kb_ids: List[str]
) -> Optional[dict]:
    """组装向量库/BM25 过滤条件。

    管理员 → None（全库可见）；无 user_id → None（调用方负责告警降级）。
    """
    if is_admin:
        return None
    if not user_id:
        return None
    if accessible_kb_ids:
        return {
            "$or": [
                {"user_id": {"$eq": user_id}},
                {"kb_id": {"$in": accessible_kb_ids}},
            ]
        }
    return {"user_id": {"$eq": user_id}}


class KBService:

    # ── 创建 / 查询 ────────────────────────────────────────────────────────────

    async def create_kb(
        self,
        owner_id: str,
        name: str,
        scope: str = "personal",
        dept_id: Optional[str] = None,
        description: str = "",
    ) -> Dict[str, Any]:
        kb_id = str(uuid.uuid4())
        async with AsyncSessionLocal() as db:
            kb = KnowledgeBase(
                kb_id=kb_id,
                name=name,
                description=description,
                owner_id=owner_id,
                scope=scope,
                dept_id=dept_id,
            )
            db.add(kb)
            db.add(KBPermission(
                kb_id=kb_id,
                principal_id=owner_id,
                principal_type="user",
                role="admin",
                granted_by=owner_id,
            ))
            await db.commit()
        logger.info(f"[KB] 创建知识库 kb_id={kb_id} name={name} owner={owner_id}")
        return {"kb_id": kb_id, "name": name, "scope": scope}

    async def get_kb(self, kb_id: str) -> Optional[KnowledgeBase]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(KnowledgeBase).where(KnowledgeBase.kb_id == kb_id)
            )
            return result.scalar_one_or_none()

    async def list_accessible_kbs(
        self, user_id: str, is_admin: bool = False, dept_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """返回用户可访问的 KB。
        管理员：全部 KB（含 admin 范围）。
        普通用户：company 范围 + 被显式授权的 KB（不含 admin 范围）。
        """
        async with AsyncSessionLocal() as db:
            if is_admin:
                rows = (await db.execute(select(KnowledgeBase))).scalars().all()
            else:
                cond = and_(
                    KBPermission.principal_id == user_id,
                    KBPermission.principal_type == "user",
                )
                if dept_id:
                    cond = or_(
                        cond,
                        and_(
                            KBPermission.principal_id == dept_id,
                            KBPermission.principal_type == "dept",
                        ),
                    )
                perm_rows = (await db.execute(select(KBPermission).where(cond))).scalars().all()
                granted_kb_ids = list({p.kb_id for p in perm_rows})

                # 可见性：被显式授权的库 + 全公司库 +（若有部门）本部门 dept 库
                visible_clause = or_(
                    KnowledgeBase.kb_id.in_(granted_kb_ids),
                    KnowledgeBase.scope == "company",
                )
                if dept_id:
                    visible_clause = or_(
                        visible_clause,
                        and_(
                            KnowledgeBase.scope == "dept",
                            KnowledgeBase.dept_id == dept_id,
                        ),
                    )

                rows = (await db.execute(
                    select(KnowledgeBase).where(
                        and_(KnowledgeBase.scope != "admin", visible_clause)
                    )
                )).scalars().all()

        return [self._kb_to_dict(kb) for kb in rows]

    async def get_accessible_kb_ids(
        self, user_id: str, is_admin: bool = False, dept_id: Optional[str] = None
    ) -> List[str]:
        kbs = await self.list_accessible_kbs(user_id, is_admin=is_admin, dept_id=dept_id)
        return [kb["kb_id"] for kb in kbs]

    async def build_accessible_filter(
        self, user_id: str, is_admin: bool = False, dept_id: Optional[str] = None
    ) -> Optional[dict]:
        """按当前身份组装检索过滤条件（agent 路径与 /rag/query 复用）。"""
        if is_admin or not user_id:
            return assemble_rag_filter(user_id, is_admin, [])
        ids = await self.get_accessible_kb_ids(user_id, is_admin=is_admin, dept_id=dept_id)
        return assemble_rag_filter(user_id, is_admin, ids)

    # ── 权限检查 ──────────────────────────────────────────────────────────────

    async def check_permission(
        self, user_id: str, kb_id: str, required_role: str = "viewer",
        is_admin: bool = False, dept_id: Optional[str] = None, is_dept_admin: bool = False,
    ) -> bool:
        async with AsyncSessionLocal() as db:
            kb_row = (await db.execute(
                select(KnowledgeBase).where(KnowledgeBase.kb_id == kb_id)
            )).scalar_one_or_none()

            if not kb_row:
                return False

            # 总管理员：跨部门全权
            if is_admin:
                return True

            # dept 范围：本部门成员只读，本部门管理员可管，他部门走显式授权
            if kb_row.scope == "dept" and dept_id and kb_row.dept_id == dept_id:
                if is_dept_admin:
                    return True
                return _ROLE_RANK.get(required_role, 0) <= _ROLE_RANK["viewer"]

            # admin 范围：仅拥有显式权限的用户可访问（普通用户一律拒绝）
            if kb_row.scope == "admin":
                perm_row = (await db.execute(
                    select(KBPermission).where(
                        and_(
                            KBPermission.kb_id == kb_id,
                            KBPermission.principal_id == user_id,
                            KBPermission.principal_type == "user",
                        )
                    )
                )).scalar_one_or_none()
                return (
                    perm_row is not None
                    and _ROLE_RANK.get(perm_row.role, 0) >= _ROLE_RANK.get(required_role, 0)
                )

            # company 范围：所有用户自动拥有 editor 及以下权限（可查询、上传）
            if kb_row.scope == "company" and _ROLE_RANK.get(required_role, 0) <= _ROLE_RANK["editor"]:
                return True

            # 检查显式授权记录
            perm_row = (await db.execute(
                select(KBPermission).where(
                    and_(
                        KBPermission.kb_id == kb_id,
                        KBPermission.principal_id == user_id,
                        KBPermission.principal_type == "user",
                    )
                )
            )).scalar_one_or_none()

            if perm_row and _ROLE_RANK.get(perm_row.role, 0) >= _ROLE_RANK.get(required_role, 0):
                return True

        return False

    # ── 成员管理 ──────────────────────────────────────────────────────────────

    async def add_member(
        self,
        kb_id: str,
        grantor_id: str,
        principal_id: str,
        principal_type: str,
        role: str,
        is_admin: bool = False,
        dept_id: Optional[str] = None,
        is_dept_admin: bool = False,
    ) -> None:
        if not await self.check_permission(
            grantor_id, kb_id, required_role="admin",
            is_admin=is_admin, dept_id=dept_id, is_dept_admin=is_dept_admin,
        ):
            raise PermissionError(f"用户 {grantor_id} 无权管理知识库 {kb_id}")

        async with AsyncSessionLocal() as db:
            existing = (await db.execute(
                select(KBPermission).where(
                    and_(
                        KBPermission.kb_id == kb_id,
                        KBPermission.principal_id == principal_id,
                        KBPermission.principal_type == principal_type,
                    )
                )
            )).scalar_one_or_none()

            if existing:
                existing.role = role
                existing.granted_by = grantor_id
            else:
                db.add(KBPermission(
                    kb_id=kb_id,
                    principal_id=principal_id,
                    principal_type=principal_type,
                    role=role,
                    granted_by=grantor_id,
                ))
            await db.commit()
        logger.info(f"[KB] 授权 kb={kb_id} → {principal_id}({principal_type}) role={role}")

    async def remove_member(
        self, kb_id: str, actor_id: str, principal_id: str, principal_type: str,
        is_admin: bool = False, dept_id: Optional[str] = None, is_dept_admin: bool = False,
    ) -> None:
        if not await self.check_permission(
            actor_id, kb_id, required_role="admin",
            is_admin=is_admin, dept_id=dept_id, is_dept_admin=is_dept_admin,
        ):
            raise PermissionError(f"用户 {actor_id} 无权管理知识库 {kb_id}")

        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                select(KBPermission).where(
                    and_(
                        KBPermission.kb_id == kb_id,
                        KBPermission.principal_id == principal_id,
                        KBPermission.principal_type == principal_type,
                    )
                )
            )).scalar_one_or_none()
            if row:
                await db.delete(row)
                await db.commit()
        logger.info(f"[KB] 移除成员 kb={kb_id} principal={principal_id}")

    # ── 更新 KB ───────────────────────────────────────────────────────────────

    async def update_kb(
        self, kb_id: str, user_id: str, name: str, description: Optional[str] = None,
        is_admin: bool = False, dept_id: Optional[str] = None, is_dept_admin: bool = False,
    ) -> Dict[str, Any]:
        """重命名知识库（需 editor 及以上权限）"""
        if not await self.check_permission(
            user_id, kb_id, required_role="editor",
            is_admin=is_admin, dept_id=dept_id, is_dept_admin=is_dept_admin,
        ):
            raise PermissionError(f"用户 {user_id} 无权修改知识库 {kb_id}")

        async with AsyncSessionLocal() as db:
            kb_row = (await db.execute(
                select(KnowledgeBase).where(KnowledgeBase.kb_id == kb_id)
            )).scalar_one_or_none()

            if not kb_row:
                raise ValueError(f"知识库 {kb_id} 不存在")

            kb_row.name = name
            if description is not None:
                kb_row.description = description
            await db.commit()
            await db.refresh(kb_row)

        logger.info(f"[KB] 更新知识库 kb_id={kb_id} name={name}")
        return self._kb_to_dict(kb_row)

    # ── 删除 KB ───────────────────────────────────────────────────────────────

    async def delete_kb(
        self, kb_id: str, user_id: str,
        is_admin: bool = False, dept_id: Optional[str] = None, is_dept_admin: bool = False,
    ) -> List[str]:
        """
        删除知识库元数据及权限记录，返回该 KB 下所有 doc_id（调用方负责清理向量）。
        """
        if not await self.check_permission(
            user_id, kb_id, required_role="admin",
            is_admin=is_admin, dept_id=dept_id, is_dept_admin=is_dept_admin,
        ):
            raise PermissionError(f"用户 {user_id} 无权删除知识库 {kb_id}")

        async with AsyncSessionLocal() as db:
            doc_ids = [
                r.doc_id for r in
                (await db.execute(
                    select(DocumentRecord).where(DocumentRecord.kb_id == kb_id)
                )).scalars().all()
            ]
            for row in (await db.execute(
                select(KBPermission).where(KBPermission.kb_id == kb_id)
            )).scalars().all():
                await db.delete(row)

            kb_row = (await db.execute(
                select(KnowledgeBase).where(KnowledgeBase.kb_id == kb_id)
            )).scalar_one_or_none()
            if kb_row:
                await db.delete(kb_row)

            await db.commit()

        logger.info(f"[KB] 删除知识库 kb_id={kb_id}，{len(doc_ids)} 个文档待清理")
        return doc_ids

    # ── 成员列表 ──────────────────────────────────────────────────────────────

    async def list_members(
        self, kb_id: str, user_id: str,
        is_admin: bool = False, dept_id: Optional[str] = None, is_dept_admin: bool = False,
    ) -> List[Dict[str, Any]]:
        if not await self.check_permission(
            user_id, kb_id, required_role="viewer",
            is_admin=is_admin, dept_id=dept_id, is_dept_admin=is_dept_admin,
        ):
            raise PermissionError(f"用户 {user_id} 无权查看知识库 {kb_id} 成员")

        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(KBPermission).where(KBPermission.kb_id == kb_id)
            )).scalars().all()

        return [
            {
                "principal_id": r.principal_id,
                "principal_type": r.principal_type,
                "role": r.role,
                "granted_by": r.granted_by,
                "granted_at": r.granted_at.isoformat() if r.granted_at else None,
            }
            for r in rows
        ]

    # ── 内部工具 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _kb_to_dict(kb: KnowledgeBase) -> Dict[str, Any]:
        return {
            "kb_id": kb.kb_id,
            "name": kb.name,
            "description": kb.description,
            "owner_id": kb.owner_id,
            "scope": kb.scope,
            "dept_id": kb.dept_id,
            "created_at": kb.created_at.isoformat() if kb.created_at else None,
        }


kb_service = KBService()
