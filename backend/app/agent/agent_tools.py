import datetime
from contextvars import ContextVar
from typing import List, Optional

from app.core.logger_handler import logger
from app.rag.rag_service import rag_service
from app.rag.reorder_service import reorder_service
from app.services.kb_service import kb_service
from app.utils.auth_utils import decode_django_jwt

# 每次 rag_summary_tools 调用后，将 citations 存入此 ContextVar
# 供 get_agent_stream_response 在 done 事件中读取
_citations_var: ContextVar[list] = ContextVar("rag_citations", default=[])

# 当前请求的 user_id，由 get_agent_stream_response 在调用前设置
_user_id_var: ContextVar[str] = ContextVar("rag_user_id", default="")


def get_rag_citations() -> list:
    return _citations_var.get()


def set_rag_user_id(user_id: str) -> None:
    _user_id_var.set(user_id)


async def _build_rag_filter() -> Optional[dict]:
    """构建当前用户可访问范围的 ChromaDB/BM25 过滤条件"""
    user_id = _user_id_var.get()
    if not user_id:
        return None
    accessible_kbs = await kb_service.list_accessible_kbs(user_id)
    accessible_kb_ids = [kb["kb_id"] for kb in accessible_kbs]
    if accessible_kb_ids:
        return {
            "$or": [
                {"user_id": {"$eq": user_id}},          # 当前用户的全部文档
                {"kb_id": {"$in": accessible_kb_ids}},  # 可访问的公开/共享 KB
            ]
        }
    return {"user_id": {"$eq": user_id}}


# ── Tool implementations ─────────────────────────────────────────────────────

async def rag_summary_tools(query: str) -> str:
    filter_meta = await _build_rag_filter()
    result = await rag_service.get_documents_and_summary(query, filter_meta=filter_meta)
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

    formatted = f"摘要: {summary}\n"
    if citations:
        formatted += "\n来源引用:\n"
        for i, c in enumerate(citations, 1):
            formatted += (
                f"{i}. 【{c.get('filename', '未知')}】"
                f"（相关度: {c.get('score', 0):.4f}）\n"
                f"   {c.get('chunk_preview', '')[:150]}\n"
            )
        # 去重保序，提醒 LLM 在最终回答末尾追加来源标注
        seen, filenames = set(), []
        for c in citations:
            fn = c.get("filename")
            if fn and fn not in seen:
                seen.add(fn)
                filenames.append(fn)
        citation_line = "参考文档：" + "".join(f"《{fn}》" for fn in filenames)
        formatted += (
            f"\n[指令] 你的最终回答必须以单独一行结尾，原样输出："
            f"{citation_line}"
        )
    return formatted


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
                "用于从向量数据库里检索文档并生成摘要，返回包含文档列表和摘要的结果。"
                "返回格式为：'摘要: [摘要内容]\\n\\n检索到的文档列表:\\n1. [文档1]\\n...'。"
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
