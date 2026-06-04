import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.models.chat_history import Base
from app.utils.auth_utils import RequestIdentity


@pytest_asyncio.fixture
async def api_client(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    import app.services.knowledge_gap_service as mod
    monkeypatch.setattr(mod, "AsyncSessionLocal", Session)

    from main import app
    from app.utils.auth_utils import get_current_identity
    app.dependency_overrides[get_current_identity] = lambda: RequestIdentity(user_id="u1", is_admin=False)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from app.services.knowledge_gap_service import knowledge_gap_service as svc
        await svc.save_gap("u1", None, "T", "问题Q", "c", "s")
        yield client

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_list_gaps_api(api_client):
    resp = await api_client.get("/api/knowledge-gaps")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 1 and data["gaps"][0]["title"] == "T"


@pytest.mark.asyncio
async def test_patch_status_api(api_client):
    gid = (await api_client.get("/api/knowledge-gaps")).json()["data"]["gaps"][0]["id"]
    resp = await api_client.patch(f"/api/knowledge-gaps/{gid}", json={"status": "resolved"})
    assert resp.status_code == 200
    again = await api_client.get("/api/knowledge-gaps?status=resolved")
    assert again.json()["data"]["total"] == 1
