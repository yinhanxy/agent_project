import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.chat_history import Base
from app.services.agent_trace_service import agent_trace_service


@pytest_asyncio.fixture
async def trace_db(monkeypatch):
    """SQLite 内存库替换 agent_trace_service 的 AsyncSessionLocal。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    import app.services.agent_trace_service as mod

    monkeypatch.setattr(mod, "AsyncSessionLocal", Session)
    yield Session
    await engine.dispose()


@pytest.mark.asyncio
async def test_save_and_list_traces(trace_db):
    sid = "test-session-trace-1"
    trace = [
        {"agent": "coordinator", "status": "done", "output": "{...}"},
        {"agent": "knowledge", "status": "done", "output": "documents=2"},
        {"agent": "finalize", "status": "done", "output": "答案..."},
    ]
    await agent_trace_service.save_traces(session_id=sid, trace=trace)
    rows = await agent_trace_service.list_by_session(sid)
    assert [r["agent_name"] for r in rows] == ["coordinator", "knowledge", "finalize"]
    assert rows[1]["status"] == "done"
