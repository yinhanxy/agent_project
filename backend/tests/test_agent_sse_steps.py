import json
import importlib

import pytest

from app.agent import agent
from app.utils.auth_utils import RequestIdentity

db_session_manager = importlib.import_module("app.services.database_session_manager")


class _FakeSessionManager:
    async def get_history(self, session_id, user_id):
        return []

    async def add_message(self, session_id, user_id, query, response):
        return None


async def _fake_agent_stream(query, history, identity=None):
    yield {
        "type": "step",
        "data": {
            "tool": "rag_summary_tools",
            "tool_input": '{"query": "LangChain"}',
            "tool_output": "检索到 2 个文档",
        },
    }
    yield {"type": "token", "data": "答案"}
    yield {
        "type": "done",
        "steps": [],
        "tokens": 12,
        "citations": [{"filename": "doc.md", "score": 0.9}],
    }


def _decode_sse_events(chunks):
    events = []
    for chunk in chunks:
        for block in chunk.strip().split("\n\n"):
            if not block.startswith("data: "):
                continue
            events.append(json.loads(block.removeprefix("data: ")))
    return events


@pytest.mark.asyncio
async def test_agent_stream_response_sends_tool_steps_to_frontend(monkeypatch):
    monkeypatch.setattr(
        db_session_manager,
        "database_session_manager",
        _FakeSessionManager(),
    )
    monkeypatch.setattr(agent.agent_loop, "stream", _fake_agent_stream)

    chunks = [
        chunk
        async for chunk in agent.get_agent_stream_response(
            "什么是 LangChain",
            "session-1",
            RequestIdentity(user_id="u1"),
        )
    ]

    events = _decode_sse_events(chunks)

    assert {
        "type": "agent_step",
        "data": {
            "id": "tool_rag_summary_tools",
            "title": "已检索知识库",
            "status": "done",
            "level": "success",
            "detail": "检索到 2 个文档",
        },
    } in events
