import pytest

from app.agent.graph.stream_bridge import translate_stream_item


class _Chunk:
    def __init__(self, content):
        self.content = content


def test_translate_finalize_token():
    item = ("messages", (_Chunk("答案片段"), {"langgraph_node": "finalize"}))
    events = list(translate_stream_item(item))
    assert events == [{"type": "token", "data": "答案片段"}]


def test_translate_drops_non_finalize_token():
    # HyDE / Knowledge 内部 LLM 的 token 不应泄漏给用户
    item = ("messages", (_Chunk("假设性文档"), {"langgraph_node": "knowledge"}))
    assert list(translate_stream_item(item)) == []


def test_translate_empty_token_ignored():
    item = ("messages", (_Chunk(""), {"langgraph_node": "finalize"}))
    assert list(translate_stream_item(item)) == []


def test_translate_custom_step_event():
    item = ("custom", {"kind": "step", "id": "answer_generated",
                       "status": "running", "level": "info", "detail": "正在生成最终回答"})
    events = list(translate_stream_item(item))
    assert events == [{
        "type": "agent_step_update",
        "data": {"id": "answer_generated", "status": "running",
                 "level": "info", "detail": "正在生成最终回答"},
    }]


def test_translate_unknown_custom_ignored():
    item = ("custom", {"kind": "debug", "msg": "noise"})
    assert list(translate_stream_item(item)) == []
