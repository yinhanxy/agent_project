import datetime
import os
import time
from contextvars import ContextVar
from typing import List, Optional

from app.core.logger_handler import logger
from app.rag.rag_service import rag_service
from app.rag.reorder_service import reorder_service
from app.services.kb_service import kb_service
from app.utils.auth_utils import decode_django_jwt, RequestIdentity

# rag_summary_tools 调用后把结构化 citations 存入此 ContextVar，
# 由 AgentLoop.stream 在「工具执行紧邻处」同步读取并固化进事件流传出。
# 切勿在 SSE 生成器主体（get_agent_stream_response）里跨异步生成器边界读取：
# ContextVar 在 async generator / @traceable 边界上不可靠传播，会读到空值，
# 这正是此前「参考来源」一直为空的根因。
_citations_var: ContextVar[list] = ContextVar("rag_citations", default=[])


def get_rag_citations() -> list:
    return _citations_var.get()


async def _build_rag_filter(identity: Optional[RequestIdentity]) -> Optional[dict]:
    """按当前请求身份构建向量库/BM25 过滤条件（部门隔离）。"""
    if not identity or not identity.user_id:
        logger.warning("[rag_summary_tools] 未拿到身份/user_id，本次检索不做用户隔离过滤")
        return None
    return await kb_service.build_accessible_filter(
        identity.user_id, is_admin=identity.is_admin, dept_id=identity.dept_id
    )


# ── Tool implementations ─────────────────────────────────────────────────────

def _rag_generation_mode() -> str:
    mode = os.getenv("RAG_GENERATION_MODE", "agent").strip().lower()
    return mode if mode in {"agent", "rag"} else "agent"


def _format_agent_context(result: dict) -> str:
    documents = result.get("documents", [])
    summary = result.get("summary", "")
    if not documents:
        return summary or "抱歉，我没有找到相关的信息。"

    formatted = (
        "检索到的文档片段如下。请只基于这些片段回答用户问题；"
        "如果片段不足以回答，请明确说明知识库信息不足。\n"
    )
    for i, doc in enumerate(documents, 1):
        formatted += f"\n【文档片段{i}】\n{doc}\n"
    formatted += "\n来源引用已由后端结构化返回给前端，不要在回答末尾手写参考文档列表。"
    return formatted


async def rag_summary_tools(query: str, identity: Optional[RequestIdentity] = None) -> str:
    total_t0 = time.perf_counter()
    mode = "unknown"
    logger.info(f"[rag_summary_tools] user_id={(identity.user_id if identity else '') or '<空>'}")
    try:
        filter_t0 = time.perf_counter()
        filter_meta = await _build_rag_filter(identity)
        logger.info(
            f"[Timing][RAGTool] stage=build_filter "
            f"duration={time.perf_counter() - filter_t0:.3f}s"
        )

        mode = _rag_generation_mode()
        rag_t0 = time.perf_counter()
        if mode == "rag":
            result = await rag_service.get_documents_and_summary(query, filter_meta=filter_meta)
        else:
            result = await rag_service.get_documents_for_agent(query, filter_meta=filter_meta)
        logger.info(
            f"[Timing][RAGTool] stage=rag_service mode={mode} "
            f"duration={time.perf_counter() - rag_t0:.3f}s"
        )

        summary = result.get("summary", "")
        citations = result.get("citations", [])
        error = result.get("error")

        _citations_var.set(citations)

        # 检索系统故障：给 LLM 明确信号，避免被误解为"知识库无此内容"
        if error == "retrieval_failed":
            detail = result.get("error_detail", "")
            logger.error(f"[rag_summary_tools] 检索系统故障: {detail}")
            return (
                "【检索工具异常】知识库检索服务暂时不可用，本次未能从知识库获取任何文档。"
                "请如实告知用户检索服务暂时不可用，建议稍后重试，不要凭借模型自身知识作答。"
            )

        if error == "summarize_failed":
            logger.warning("[rag_summary_tools] 摘要阶段失败，文档已检索到但未能生成摘要")

        if mode == "agent":
            return _format_agent_context(result)

        formatted = f"摘要: {summary}\n"
        if citations:
            formatted += "\n来源引用:\n"
            for i, c in enumerate(citations, 1):
                formatted += (
                    f"{i}. 【{c.get('filename', '未知')}】"
                    f"（相关度: {c.get('score', 0):.4f}）\n"
                    f"   {c.get('chunk_preview', '')[:150]}\n"
                )
        return formatted
    finally:
        logger.info(
            f"[Timing][RAGTool] stage=total mode={mode} "
            f"duration={time.perf_counter() - total_t0:.3f}s"
        )


async def reorder_documents_tools(query: str, documents: List[str]) -> str:
    result = await reorder_service.reorder_documents(query, documents)
    if result["success"]:
        formatted = await reorder_service.format_reorder_result(result["documents"])
        logger.info(formatted)
        return formatted
    return f"重排序失败: {result['error']}"


async def get_user_info_tools(token: str) -> str:
    payload = decode_django_jwt(token)
    if payload:
        user_id = payload.get("user_id", "未知")
        user_name = payload.get("user_name", "未知")
        return f"用户信息：\n- 用户ID: {user_id}\n- 用户名: {user_name}"
    return "无法解析JWT token，无法获取用户信息"


async def get_weather_tools(city: str = None) -> str:
    if not city:
        return "请提供城市名称"
    return f"【{city}】的天气是晴朗的"


async def what_time_is_now() -> str:
    return f"当前时间是：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"


# ── Tool registry ─────────────────────────────────────────────────────────────

# name -> async callable
TOOLS: dict = {
    "rag_summary_tools": rag_summary_tools,
    "reorder_documents_tools": reorder_documents_tools,
    "get_user_info_tools": get_user_info_tools,
    "get_weather_tools": get_weather_tools,
    "what_time_is_now": what_time_is_now,
}

# OpenAI function calling format
TOOL_SCHEMAS: list = [
    {
        "type": "function",
        "function": {
            "name": "rag_summary_tools",
            "description": (
                "用于从向量数据库里检索文档。默认返回已重排序的文档片段，"
                "由你基于片段生成最终回答；当系统配置为 RAG 生成模式时会返回摘要。"
                "来源引用由后端结构化返回给前端，不要手写参考文档列表。"
                "注意：文档已经过自动重排序，无需再调用重排序工具。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "用户的查询语句"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reorder_documents_tools",
            "description": (
                "用于对文档列表进行重排序，传入查询语句和文档列表，返回重排序后的结果。"
                "注意：rag_summary_tools已内置重排序功能，通常不需要单独调用此工具。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "查询语句"},
                    "documents": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "文档内容列表",
                    },
                },
                "required": ["query", "documents"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_info_tools",
            "description": "当用户明确询问自己的ID和用户名时，从JWT中解析并返回用户信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "token": {"type": "string", "description": "完整的JWT token字符串"}
                },
                "required": ["token"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather_tools",
            "description": "用于获取指定城市的天气信息，需要从用户输入中提取城市名称",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名称"}
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "what_time_is_now",
            "description": "用于获取当前年月日时分",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]
