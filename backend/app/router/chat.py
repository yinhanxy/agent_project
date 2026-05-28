from typing import List
import asyncio
import uuid
import os

import requests
from fastapi.routing import APIRouter
from fastapi import UploadFile, File, Depends, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.agent.agent import get_agent_stream_response
from app.router.chat_service import ChatService, get_router_service

from app.schemas.models import (
    QueryRequest, RAGResponse, RAGRequest, SessionResponse,
    ReorderResponse, ReorderRequest, DocumentListResponse, DocumentInfo,
    KBCreateRequest, KBInfo, KBListResponse, KBMemberRequest,
    KBQueryRequest, KBQueryResponse, Citation, KBUpdateRequest,
)
from app.utils.auth_utils import get_current_user_id, get_current_user_is_admin
from app.core.success_response import success_response
from app.core.rate_limit import rate_limit

_bearer = HTTPBearer()

chat_router = APIRouter(prefix="/api", tags=["api"])

DJANGO_API_URL = os.getenv("DJANGO_API_URL", "http://localhost:8001")


@chat_router.get("/admin/users")
async def admin_list_users(
    is_admin: bool = Depends(get_current_user_is_admin),
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
):
    """管理员：获取所有用户列表"""
    if not is_admin:
        raise HTTPException(status_code=403, detail="无权限")
    loop = asyncio.get_event_loop()
    resp = await loop.run_in_executor(
        None,
        lambda: requests.get(
            f"{DJANGO_API_URL}/user/list/",
            headers={"Authorization": f"Bearer {credentials.credentials}"},
            proxies={"http": None, "https": None},
            timeout=15,
        ),
    )
    return resp.json()


@chat_router.patch("/admin/users/{user_uuid}/set-admin")
async def admin_set_admin(
    user_uuid: str,
    is_admin: bool = Depends(get_current_user_is_admin),
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
):
    """管理员：切换用户管理员权限"""
    if not is_admin:
        raise HTTPException(status_code=403, detail="无权限")
    loop = asyncio.get_event_loop()
    resp = await loop.run_in_executor(
        None,
        lambda: requests.patch(
            f"{DJANGO_API_URL}/user/{user_uuid}/set-admin/",
            headers={"Authorization": f"Bearer {credentials.credentials}"},
            proxies={"http": None, "https": None},
            timeout=15,
        ),
    )
    return resp.json()

@chat_router.post("/agent/query/stream")
async def query_stream(
        request: QueryRequest,
        user_id: str = Depends(get_current_user_id),
        _: None = Depends(rate_limit(limit=10, window=60))
):
    """查询Agent流式响应"""
    # 如果没有提供session_id，自动生成一个
    session_id = request.session_id or str(uuid.uuid4())
    
    # 直接调用get_agent_stream_response函数
    return StreamingResponse(
        get_agent_stream_response(request.query, session_id, user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )


@chat_router.post("/rag/query", response_model=RAGResponse)
async def query_rag(
        request: RAGRequest,
        router_service: ChatService = Depends(get_router_service),
        _: None = Depends(rate_limit(limit=15, window=60))
):
    """RAG 检索（返回摘要 + 来源引用）"""
    result = await router_service.handle_rag_query_with_citations(request.query)
    if result.get("error") == "retrieval_failed":
        raise HTTPException(status_code=503, detail=result.get("summary", "检索服务暂时不可用"))
    citations = [Citation(**c) for c in result.get("citations", [])]
    return success_response(data=RAGResponse(response=result["summary"], citations=citations))


@chat_router.get("/session/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, user_id: str = Depends(get_current_user_id), router_service: ChatService = Depends(get_router_service)):
    """获取会话信息，使用user_id验证"""
    history = await router_service.handle_get_session(session_id, user_id)
    return success_response(data=SessionResponse(session_id=session_id, history=history))



@chat_router.delete("/session/{session_id}")
async def delete_session(session_id: str, user_id: str = Depends(get_current_user_id), router_service: ChatService = Depends(get_router_service)):
    """删除会话"""
    await router_service.handle_delete_session(session_id, user_id)
    return success_response(message=f"Session {session_id} deleted successfully")

@chat_router.get("/sessions")
async def get_all_sessions(
    is_admin: bool = Depends(get_current_user_is_admin),
    router_service: ChatService = Depends(get_router_service),
):
    """获取所有会话ID（仅管理员）"""
    if not is_admin:
        raise HTTPException(status_code=403, detail="无权限")
    session_ids = await router_service.handle_get_all_sessions()
    return success_response(data={"sessions": session_ids})



@chat_router.get("/sessions/{user_id}")
async def get_user_sessions(user_id: str, current_user_id: str = Depends(get_current_user_id), router_service: ChatService = Depends(get_router_service)):
    """获取用户所有会话ID"""
    session_ids = await router_service.handle_get_user_sessions(user_id, current_user_id)
    return success_response(data={"sessions": session_ids})


@chat_router.post("/vector/add/single")
async def add_vector_single(
        file: UploadFile = File(...),
        user_id: str = Depends(get_current_user_id),
        router_service: ChatService = Depends(get_router_service),
        _: None = Depends(rate_limit(limit=30, window=60))
):
    """上传文件，将文件保存到向量数据库，仅支持TXT和PDF"""
    filename = await router_service.handle_add_vector_single(file, user_id)
    return success_response(message=f"文件 {filename} 已成功上传并存储到向量数据库")



@chat_router.post("/vector/add/multiple")
async def add_vector_multiple(
        files: List[UploadFile] = File(..., description="要上传的文件列表，仅支持PDF和TXT格式"),
        user_id: str = Depends(get_current_user_id),
        router_service: ChatService = Depends(get_router_service),
        _: None = Depends(rate_limit(limit=30, window=60))
):
    """上传多个文件，将文件保存到向量数据库，仅支持TXT和PDF"""
    filenames = await router_service.handle_add_vector_multiple(files, user_id)
    return success_response(message=f"文件 {filenames} 已成功上传并存储到向量数据库")


@chat_router.delete("/vector/clean")
async def clean_user_vectors(
    user_id: str = Depends(get_current_user_id),
    router_service: ChatService = Depends(get_router_service),
):
    """清空用户知识库（向量 + 元数据记录一并删除）"""
    await router_service.clean_user_upload(user_id)
    return success_response(message="已成功清空知识库")


@chat_router.get("/vector/list")
async def list_documents(
    user_id: str = Depends(get_current_user_id),
    router_service: ChatService = Depends(get_router_service),
):
    """获取当前用户的知识库文档列表"""
    docs = await router_service.handle_list_documents(user_id)
    return success_response(
        data=DocumentListResponse(
            documents=[DocumentInfo(**d) for d in docs],
            total=len(docs),
        )
    )


@chat_router.delete("/vector/document/{doc_id}")
async def delete_document(
    doc_id: str,
    user_id: str = Depends(get_current_user_id),
    router_service: ChatService = Depends(get_router_service),
):
    """删除知识库中的单个文档"""
    await router_service.handle_delete_document(doc_id, user_id)
    return success_response(message=f"文档 {doc_id} 已删除")


@chat_router.post("/reorder", response_model=ReorderResponse)
async def reorder_documents(
        request: ReorderRequest,
        router_service: ChatService = Depends(get_router_service),
        _: None = Depends(rate_limit(limit=20, window=60))
):
    """使用Ollama本地的嵌入模型对文档进行中文重排序"""
    sorted_docs = await router_service.handle_reorder(request.query, request.documents)
    return success_response(data=ReorderResponse(documents=sorted_docs))


# ── 知识库管理 ─────────────────────────────────────────────────────────────────

@chat_router.post("/kb")
async def create_kb(
    request: KBCreateRequest,
    user_id: str = Depends(get_current_user_id),
    is_admin: bool = Depends(get_current_user_is_admin),
    router_service: ChatService = Depends(get_router_service),
):
    """创建知识库（company/dept 范围仅管理员可创建）"""
    kb = await router_service.handle_create_kb(
        user_id=user_id,
        name=request.name,
        scope=request.scope,
        dept_id=request.dept_id,
        description=request.description,
        is_admin=is_admin,
    )
    return success_response(data=kb)


@chat_router.get("/kb/list")
async def list_kbs(
    user_id: str = Depends(get_current_user_id),
    is_admin: bool = Depends(get_current_user_is_admin),
    router_service: ChatService = Depends(get_router_service),
):
    """列出用户可访问的知识库（管理员返回全部，普通用户仅返回公开）"""
    kbs = await router_service.handle_list_kbs(user_id, is_admin=is_admin)
    return success_response(
        data={"kbs": [KBInfo(**kb) for kb in kbs], "total": len(kbs), "is_admin": is_admin}
    )


@chat_router.get("/kb/{kb_id}")
async def get_kb(
    kb_id: str,
    user_id: str = Depends(get_current_user_id),
    router_service: ChatService = Depends(get_router_service),
):
    """获取知识库详情"""
    kb = await router_service.handle_get_kb(kb_id, user_id)
    return success_response(data=KBInfo(**kb))


@chat_router.patch("/kb/{kb_id}")
async def update_kb(
    kb_id: str,
    request: KBUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    router_service: ChatService = Depends(get_router_service),
):
    """重命名知识库（需 editor 以上权限）"""
    kb = await router_service.handle_update_kb(kb_id, user_id, request.name, request.description)
    return success_response(data=KBInfo(**kb))


@chat_router.delete("/kb/{kb_id}")
async def delete_kb(
    kb_id: str,
    user_id: str = Depends(get_current_user_id),
    router_service: ChatService = Depends(get_router_service),
):
    """删除知识库（仅 admin）"""
    await router_service.handle_delete_kb(kb_id, user_id)
    return success_response(message=f"知识库 {kb_id} 已删除")


@chat_router.post("/kb/{kb_id}/members")
async def add_kb_member(
    kb_id: str,
    request: KBMemberRequest,
    user_id: str = Depends(get_current_user_id),
    router_service: ChatService = Depends(get_router_service),
):
    """添加 / 更新知识库成员权限（仅 admin）"""
    await router_service.handle_add_kb_member(
        kb_id=kb_id,
        actor_id=user_id,
        principal_id=request.principal_id,
        principal_type=request.principal_type,
        role=request.role,
    )
    return success_response(message="成员权限已更新")


@chat_router.delete("/kb/{kb_id}/members/{principal_id}")
async def remove_kb_member(
    kb_id: str,
    principal_id: str,
    principal_type: str = "user",
    user_id: str = Depends(get_current_user_id),
    router_service: ChatService = Depends(get_router_service),
):
    """移除知识库成员（仅 admin）"""
    await router_service.handle_remove_kb_member(kb_id, user_id, principal_id, principal_type)
    return success_response(message="成员已移除")


@chat_router.get("/kb/{kb_id}/members")
async def list_kb_members(
    kb_id: str,
    user_id: str = Depends(get_current_user_id),
    router_service: ChatService = Depends(get_router_service),
):
    """获取知识库成员列表"""
    members = await router_service.handle_list_kb_members(kb_id, user_id)
    return success_response(data={"members": members, "total": len(members)})


@chat_router.get("/kb/{kb_id}/documents")
async def list_kb_documents(
    kb_id: str,
    user_id: str = Depends(get_current_user_id),
    router_service: ChatService = Depends(get_router_service),
):
    """获取知识库文档列表"""
    docs = await router_service.handle_list_kb_documents(kb_id, user_id)
    return success_response(
        data=DocumentListResponse(
            documents=[DocumentInfo(**d) for d in docs],
            total=len(docs),
        )
    )


@chat_router.post("/kb/{kb_id}/documents")
async def upload_to_kb(
    kb_id: str,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
    router_service: ChatService = Depends(get_router_service),
    _: None = Depends(rate_limit(limit=30, window=60)),
):
    """上传文档到指定知识库（需 editor 以上权限）"""
    filename = await router_service.handle_add_vector_single(file, user_id, kb_id=kb_id)
    return success_response(message=f"文件 {filename} 已成功上传到知识库 {kb_id}")


@chat_router.post("/kb/{kb_id}/query", response_model=KBQueryResponse)
async def query_kb(
    kb_id: str,
    request: KBQueryRequest,
    user_id: str = Depends(get_current_user_id),
    router_service: ChatService = Depends(get_router_service),
    _: None = Depends(rate_limit(limit=15, window=60)),
):
    """在指定知识库中检索（需 viewer 以上权限），返回摘要 + 来源引用"""
    result = await router_service.handle_kb_query(kb_id, request.query, user_id)
    if result.get("error") == "retrieval_failed":
        raise HTTPException(status_code=503, detail=result.get("summary", "检索服务暂时不可用"))
    citations = [Citation(**c) for c in result.get("citations", [])]
    return success_response(data=KBQueryResponse(
        summary=result.get("summary", ""),
        citations=citations,
        documents=result.get("documents", []),
    ))