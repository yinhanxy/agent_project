import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.models.chat_history import Base


@pytest_asyncio.fixture
async def sqlite_db(monkeypatch):
    """用 SQLite 内存库替换 kb_service 的 AsyncSessionLocal，做 DB 集成测试。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    import app.services.kb_service as kb_mod
    monkeypatch.setattr(kb_mod, "AsyncSessionLocal", Session)

    yield Session
    await engine.dispose()
