import asyncio
import time
from typing import List, Optional, Tuple, Dict, Any
import uuid
import magic
import os

from fastapi import HTTPException, UploadFile

from app.core.logger_handler import logger
from app.rag.vector_store import VectorStoreService
from app.rag.rag_service import rag_service
from app.rag.reorder_service import reorder_service
from app.services import session_manager as sm
from app.services.document_service import document_service
from app.services.kb_service import kb_service, can_create_kb
from app.utils.auth_utils import RequestIdentity


ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".pptx", ".docx"}
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
MAX_SINGLE_SIZE = 20 * 1024 * 1024   # 20 MB
MAX_BATCH_SIZE = 200 * 1024 * 1024   # 200 MB


def _check_file_type(content: bytes, filename: str) -> None:
    """MIME + 扩展名双重校验，不通过则抛 400。
    libmagic 对含有类定义代码的文本文件可能触发内存耗尽异常，
    此时降级为纯扩展名校验。
    """
    ext = os.path.splitext(filename)[1].lower()
    try:
        mime = magic.Magic(mime=True)
        file_type = mime.from_buffer(content)
        if file_type not in ALLOWED_MIME_TYPES and ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件类型：{filename}（检测到 {file_type}，扩展名 {ext}）",
            )
    except HTTPException:
        raise
    except Exception as e:
        # libmagic 在某些含代码示例的文本文件上会触发 regex 内存溢出
        # 降级为纯扩展名校验
        logger.warning(f"[FileCheck] libmagic 检测失败，降级为扩展名校验: {filename} — {e}")
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件类型：{filename}（扩展名 {ext} 不在允许列表中）",
            )


class ChatService:
    """路由服务层，处理业务逻辑"""

    # ── 对话 ──────────────────────────────────────────────────────────────────

    async def handle_rag_query(self, query: str) -> str:
        return await rag_service.rag_summary(query)

    async def handle_rag_query_with_citations(
        self, query: str, identity: RequestIdentity
    ) -> Dict[str, Any]:
        # 与 agent 路径一致的用户/部门过滤，避免全库越权检索
        filter_meta = await kb_service.build_accessible_filter(
            identity.user_id, is_admin=identity.is_admin, dept_id=identity.dept_id,
        )
        return await rag_service.get_documents_and_summary(query, filter_meta=filter_meta)

    # ── 会话管理 ──────────────────────────────────────────────────────────────

    async def handle_get_session(self, session_id: str, user_id: str):
        return await sm.session_manager.get_session(session_id, user_id)

    async def handle_delete_session(self, session_id: str, user_id: str) -> None:
        await sm.session_manager.clear_session(session_id, user_id)

    async def handle_ensure_session_writable(self, session_id: str, user_id: str) -> None:
        await sm.session_manager.ensure_session_writable(session_id, user_id)

    async def handle_archive_session(self, session_id: str, user_id: str, archived: bool) -> Dict:
        return await sm.session_manager.set_session_archived(session_id, user_id, archived)

    async def handle_get_all_sessions(self) -> List[str]:
        return await sm.session_manager.get_all_session_ids()

    async def handle_get_user_sessions(self, user_id: str, current_user_id: str, archived: bool = False) -> List[Dict]:
        if user_id != current_user_id:
            raise HTTPException(status_code=403, detail="Forbidden")
        return await sm.session_manager.get_user_sessions(user_id, archived=archived)

    # ── 知识库：上传 ──────────────────────────────────────────────────────────

    async def handle_add_vector_single(
        self, file: UploadFile, identity: RequestIdentity, kb_id: str = None
    ) -> str:
        user_id = identity.user_id
        if file.size and file.size > MAX_SINGLE_SIZE:
            raise HTTPException(status_code=400, detail="文件大小不能超过 20MB")

        content = await file.read()
        await file.seek(0)
        _check_file_type(content, file.filename)

        if kb_id:
            has_perm = await kb_service.check_permission(
                user_id, kb_id, required_role="editor",
                is_admin=identity.is_admin, dept_id=identity.dept_id,
                is_dept_admin=identity.is_dept_admin,
            )
            if not has_perm:
                raise HTTPException(status_code=403, detail=f"无权向知识库 {kb_id} 上传文件")

        store = VectorStoreService()
        result = await store.get_document(files=[file], user_id=user_id, replace=True, kb_id=kb_id)
        if not result["processed"]:
            if result["duplicates"]:
                raise HTTPException(
                    status_code=409,
                    detail=f"文件 {file.filename} 已存在于知识库中，无需重复上传",
                )
            raise HTTPException(
                status_code=422,
                detail=f"文件 {file.filename} 处理失败，可能是内容为空或格式不支持",
            )
        rag_service.invalidate_retriever()
        return file.filename

    async def handle_add_vector_multiple(
        self, files: List[UploadFile], identity: RequestIdentity, kb_id: str = None
    ) -> List[str]:
        user_id = identity.user_id
        total_size = 0
        for file in files:
            content = await file.read()
            total_size += len(content)
            _check_file_type(content, file.filename)
            await file.seek(0)

        if total_size > MAX_BATCH_SIZE:
            raise HTTPException(status_code=400, detail="文件总大小不能超过 200MB")

        if kb_id:
            has_perm = await kb_service.check_permission(
                user_id, kb_id, required_role="editor",
                is_admin=identity.is_admin, dept_id=identity.dept_id,
                is_dept_admin=identity.is_dept_admin,
            )
            if not has_perm:
                raise HTTPException(status_code=403, detail=f"无权向知识库 {kb_id} 上传文件")

        start = time.time()

        async def process(f: UploadFile) -> str:
            s = VectorStoreService()
            result = await s.get_document(files=[f], user_id=user_id, replace=True, kb_id=kb_id)
            if not result["processed"]:
                if result["duplicates"]:
                    raise HTTPException(
                        status_code=409,
                        detail=f"文件 {f.filename} 已存在于知识库中，无需重复上传",
                    )
                raise HTTPException(
                    status_code=422,
                    detail=f"文件 {f.filename} 处理失败，可能是内容为空或格式不支持",
                )
            return f.filename

        results = await asyncio.gather(*[process(f) for f in files])
        rag_service.invalidate_retriever()
        logger.info(f"[VectorUpload] 批量上传 {len(results)} 个文件，耗时 {time.time()-start:.2f}s")
        return list(results)

    # ── 知识库：查询 ──────────────────────────────────────────────────────────

    async def handle_list_documents(self, user_id: str) -> List[Dict[str, Any]]:
        """返回用户知识库文档列表"""
        return await document_service.list_by_user(user_id)

    # ── 知识库：删除 ──────────────────────────────────────────────────────────

    async def handle_delete_document(self, doc_id: str, user_id: str) -> None:
        """删除单个文档"""
        store = VectorStoreService()
        deleted = await store.delete_document_by_id(doc_id, user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="文档不存在或无权限删除")
        rag_service.invalidate_retriever()

    async def clean_user_upload(self, user_id: str) -> None:
        """清空用户全部文档（向量库 + DB 记录一并清除，修复旧版 MD5 遗留 Bug）"""
        store = VectorStoreService()
        await store.delete_user_documents(user_id)
        rag_service.invalidate_retriever()

    # ── 知识库管理 ────────────────────────────────────────────────────────────

    async def handle_create_kb(
        self, identity: RequestIdentity, name: str, scope: str,
        dept_id: Optional[str], description: str,
    ) -> Dict[str, Any]:
        allowed, eff_dept = can_create_kb(
            scope, identity.is_admin, identity.is_dept_admin,
            identity.dept_id, dept_id,
        )
        if not allowed:
            raise HTTPException(status_code=403, detail="无权创建该范围/部门的知识库")
        return await kb_service.create_kb(
            owner_id=identity.user_id, name=name, scope=scope,
            dept_id=eff_dept, description=description,
        )

    async def handle_list_kbs(self, identity: RequestIdentity) -> List[Dict[str, Any]]:
        return await kb_service.list_accessible_kbs(
            identity.user_id, is_admin=identity.is_admin, dept_id=identity.dept_id,
        )

    async def handle_get_kb(self, kb_id: str, identity: RequestIdentity) -> Dict[str, Any]:
        has_perm = await kb_service.check_permission(
            identity.user_id, kb_id, required_role="viewer",
            is_admin=identity.is_admin, dept_id=identity.dept_id,
            is_dept_admin=identity.is_dept_admin,
        )
        if not has_perm:
            raise HTTPException(status_code=403, detail="无权访问该知识库")
        kb = await kb_service.get_kb(kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在")
        return kb_service._kb_to_dict(kb)

    async def handle_update_kb(
        self, kb_id: str, identity: RequestIdentity, name: str, description: Optional[str]
    ) -> Dict[str, Any]:
        try:
            return await kb_service.update_kb(
                kb_id, identity.user_id, name, description,
                is_admin=identity.is_admin, dept_id=identity.dept_id,
                is_dept_admin=identity.is_dept_admin,
            )
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    async def handle_delete_kb(self, kb_id: str, identity: RequestIdentity) -> None:
        try:
            doc_ids = await kb_service.delete_kb(
                kb_id, identity.user_id,
                is_admin=identity.is_admin, dept_id=identity.dept_id,
                is_dept_admin=identity.is_dept_admin,
            )
            store = VectorStoreService()
            for doc_id in doc_ids:
                await store.delete_document_by_id(doc_id, identity.user_id)
            rag_service.invalidate_retriever()
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e))

    async def handle_add_kb_member(
        self, kb_id: str, identity: RequestIdentity,
        principal_id: str, principal_type: str, role: str
    ) -> None:
        try:
            await kb_service.add_member(
                kb_id, identity.user_id, principal_id, principal_type, role,
                is_admin=identity.is_admin, dept_id=identity.dept_id,
                is_dept_admin=identity.is_dept_admin,
            )
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e))

    async def handle_remove_kb_member(
        self, kb_id: str, identity: RequestIdentity, principal_id: str, principal_type: str
    ) -> None:
        try:
            await kb_service.remove_member(
                kb_id, identity.user_id, principal_id, principal_type,
                is_admin=identity.is_admin, dept_id=identity.dept_id,
                is_dept_admin=identity.is_dept_admin,
            )
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e))

    async def handle_list_kb_members(
        self, kb_id: str, identity: RequestIdentity
    ) -> List[Dict[str, Any]]:
        try:
            return await kb_service.list_members(
                kb_id, identity.user_id,
                is_admin=identity.is_admin, dept_id=identity.dept_id,
                is_dept_admin=identity.is_dept_admin,
            )
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e))

    async def handle_list_kb_documents(
        self, kb_id: str, identity: RequestIdentity
    ) -> List[Dict[str, Any]]:
        has_perm = await kb_service.check_permission(
            identity.user_id, kb_id, required_role="viewer",
            is_admin=identity.is_admin, dept_id=identity.dept_id,
            is_dept_admin=identity.is_dept_admin,
        )
        if not has_perm:
            raise HTTPException(status_code=403, detail="无权访问该知识库")
        return await document_service.list_by_kb(kb_id)

    async def handle_kb_query(
        self, kb_id: str, query: str, identity: RequestIdentity
    ) -> Dict[str, Any]:
        has_perm = await kb_service.check_permission(
            identity.user_id, kb_id, required_role="viewer",
            is_admin=identity.is_admin, dept_id=identity.dept_id,
            is_dept_admin=identity.is_dept_admin,
        )
        if not has_perm:
            raise HTTPException(status_code=403, detail="无权查询该知识库")
        filter_meta = {"kb_id": kb_id}
        return await rag_service.get_documents_and_summary(query, filter_meta=filter_meta)

    # ── 重排序 ────────────────────────────────────────────────────────────────

    async def handle_reorder(
        self, query: str, documents: List[str]
    ) -> List[Dict[str, Any]]:
        try:
            result = await reorder_service.reorder_documents(query, documents)
            if result["success"]:
                logger.info(
                    f"[Reorder] 排序结果: "
                    + str([f"{d['document'][:20]}: {d['similarity']:.4f}" for d in result["documents"]])
                )
                return result["documents"]
            logger.warning(f"[Reorder] 失败: {result['error']}")
            return [{"document": d, "similarity": 0.0} for d in documents]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"重排序失败: {e}")


def get_router_service() -> ChatService:
    return ChatService()
