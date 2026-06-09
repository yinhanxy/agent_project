"""Agent 共享 token 估算工具。

抽出来避免 app.agent.agent 与 app.agent.graph.runner 互相依赖时的循环导入。
"""
from typing import Iterable

from app.core.logger_handler import logger

_token_encoder = None


def _get_encoder():
    global _token_encoder
    if _token_encoder is None:
        try:
            import tiktoken
            _token_encoder = tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            logger.warning(f"[token估算] tiktoken 不可用，降级为字符估算: {e}")
            _token_encoder = False
    return _token_encoder


def estimate_text_tokens(text: str) -> int:
    if not text:
        return 0
    enc = _get_encoder()
    if enc:
        return len(enc.encode(text))
    return max(1, len(text) // 2)


def estimate_messages_tokens(messages: Iterable[dict]) -> int:
    total = 0
    for m in messages:
        content = m.get("content") if isinstance(m, dict) else None
        if isinstance(content, str):
            total += estimate_text_tokens(content)
        if isinstance(m, dict):
            for tc in m.get("tool_calls") or []:
                total += estimate_text_tokens(
                    tc.get("function", {}).get("arguments", "")
                )
        total += 4
    return total


def estimate_history_query_tokens(history: list, query: str) -> int:
    """估算 (history + query) 的 token 数。history 形如 [(user, assistant), ...]。"""
    msgs: list[dict] = []
    for pair in history or []:
        if isinstance(pair, (list, tuple)) and len(pair) == 2:
            user_msg, assistant_msg = pair
            msgs.append({"role": "user", "content": user_msg or ""})
            msgs.append({"role": "assistant", "content": assistant_msg or ""})
    msgs.append({"role": "user", "content": query or ""})
    return estimate_messages_tokens(msgs)


def extract_total_tokens(message):
    """从 LangChain message/chunk 上抠 total_tokens；拿不到返回 None（由调用方估算兜底）。"""
    if message is None:
        return None
    usage = getattr(message, "usage_metadata", None)
    if isinstance(usage, dict):
        total = usage.get("total_tokens")
        if total:
            return int(total)
    rmeta = getattr(message, "response_metadata", None)
    if isinstance(rmeta, dict):
        token_usage = rmeta.get("token_usage") or rmeta.get("usage")
        if isinstance(token_usage, dict):
            total = token_usage.get("total_tokens")
            if total:
                return int(total)
    return None
