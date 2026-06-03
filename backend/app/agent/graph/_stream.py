"""图节点共享的 stream writer 工具。"""
from langgraph.config import get_stream_writer


def safe_get_stream_writer():
    """在没有 LangGraph 运行时上下文时（如单元测试）返回 no-op writer。"""
    try:
        return get_stream_writer()
    except RuntimeError:
        return lambda _: None
