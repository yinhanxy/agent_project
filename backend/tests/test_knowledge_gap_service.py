import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.models.chat_history import Base


@pytest_asyncio.fixture
async def gap_db(monkeypatch):
    """SQLite 内存库替换 knowledge_gap_service 的 AsyncSessionLocal。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    import app.services.knowledge_gap_service as mod
    monkeypatch.setattr(mod, "AsyncSessionLocal", Session)
    yield Session
    await engine.dispose()


@pytest.mark.asyncio
async def test_save_then_list(gap_db):
    from app.services.knowledge_gap_service import knowledge_gap_service as svc
    await svc.save_gap("u1", "d1", "设备报销", "远程办公设备损坏怎么报销", "财务", "建议补充1.2.3")
    gaps = await svc.list_gaps("u1", is_admin=False)
    assert len(gaps) == 1
    assert gaps[0]["title"] == "设备报销" and gaps[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_dedup_same_question_pending(gap_db):
    from app.services.knowledge_gap_service import knowledge_gap_service as svc
    await svc.save_gap("u1", None, "T", "同一个问题", "c", "s1")
    await svc.save_gap("u1", None, "T2", "同一个问题", "c", "s2")
    gaps = await svc.list_gaps("u1", is_admin=False)
    assert len(gaps) == 1


@pytest.mark.asyncio
async def test_list_filters_by_user_for_non_admin(gap_db):
    from app.services.knowledge_gap_service import knowledge_gap_service as svc
    await svc.save_gap("u1", None, "T", "问题A", "c", "s")
    await svc.save_gap("u2", None, "T", "问题B", "c", "s")
    assert len(await svc.list_gaps("u1", is_admin=False)) == 1
    assert len(await svc.list_gaps("u1", is_admin=True)) == 2


@pytest.mark.asyncio
async def test_update_status_and_permission(gap_db):
    from app.services.knowledge_gap_service import knowledge_gap_service as svc
    await svc.save_gap("u1", None, "T", "问题X", "c", "s")
    gid = (await svc.list_gaps("u1", is_admin=False))[0]["id"]
    assert await svc.update_status(gid, "u1", is_admin=False, status="resolved") is True
    assert (await svc.list_gaps("u1", is_admin=True))[0]["status"] == "resolved"
    with pytest.raises(PermissionError):
        await svc.update_status(gid, "u2", is_admin=False, status="ignored")


@pytest.mark.asyncio
async def test_update_status_rejects_invalid(gap_db):
    from app.services.knowledge_gap_service import knowledge_gap_service as svc
    with pytest.raises(ValueError):
        await svc.update_status(1, "u1", is_admin=True, status="not_a_status")
