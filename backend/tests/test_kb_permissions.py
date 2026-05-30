import pytest

from app.services.kb_service import can_create_kb, assemble_rag_filter


# ── can_create_kb 纯函数 ──────────────────────────────────────────────────────

def test_personal_anyone():
    assert can_create_kb("personal", is_admin=False, is_dept_admin=False,
                         user_dept_id=None, req_dept_id=None) == (True, None)


def test_company_admin_only():
    assert can_create_kb("company", False, False, "d1", None)[0] is False
    assert can_create_kb("company", True, False, None, None) == (True, None)


def test_admin_scope_admin_only():
    assert can_create_kb("admin", False, True, "d1", "d1")[0] is False
    assert can_create_kb("admin", True, False, None, None) == (True, None)


def test_dept_super_admin_targets_any_dept():
    assert can_create_kb("dept", True, False, None, "dX") == (True, "dX")


def test_dept_admin_own_dept():
    # 部门管理员建本部门库：未传 dept_id 时回填自身部门
    assert can_create_kb("dept", False, True, "d1", None) == (True, "d1")
    assert can_create_kb("dept", False, True, "d1", "d1") == (True, "d1")


def test_dept_admin_cannot_target_other_dept():
    assert can_create_kb("dept", False, True, "d1", "d2")[0] is False


def test_dept_plain_member_denied():
    assert can_create_kb("dept", False, False, "d1", "d1")[0] is False


def test_unknown_scope_denied():
    assert can_create_kb("weird", True, False, None, None)[0] is False


# ── assemble_rag_filter 纯函数 ────────────────────────────────────────────────

def test_filter_admin_no_filter():
    assert assemble_rag_filter("u1", is_admin=True, accessible_kb_ids=["k1"]) is None


def test_filter_no_user_id_returns_none():
    assert assemble_rag_filter("", is_admin=False, accessible_kb_ids=["k1"]) is None


def test_filter_with_kb_ids():
    f = assemble_rag_filter("u1", False, ["k1", "k2"])
    assert f == {"$or": [{"user_id": {"$eq": "u1"}}, {"kb_id": {"$in": ["k1", "k2"]}}]}


def test_filter_without_kb_ids_personal_only():
    assert assemble_rag_filter("u1", False, []) == {"user_id": {"$eq": "u1"}}


# ── DB 集成：list_accessible_kbs 部门可见性 ──────────────────────────────────

pytest.importorskip("aiosqlite")
from app.services.kb_service import kb_service  # noqa: E402


async def test_dept_member_sees_own_dept_kb(sqlite_db):
    await kb_service.create_kb("owner", "d1库", scope="dept", dept_id="d1")
    await kb_service.create_kb("owner", "d2库", scope="dept", dept_id="d2")
    kbs = await kb_service.list_accessible_kbs("member", is_admin=False, dept_id="d1")
    names = {k["name"] for k in kbs}
    assert "d1库" in names           # 本部门库自动可见
    assert "d2库" not in names       # 他部门库不可见


async def test_no_dept_user_sees_no_dept_kb(sqlite_db):
    await kb_service.create_kb("owner", "d1库", scope="dept", dept_id="d1")
    kbs = await kb_service.list_accessible_kbs("member", is_admin=False, dept_id=None)
    assert "d1库" not in {k["name"] for k in kbs}


async def test_company_kb_visible_to_all(sqlite_db):
    await kb_service.create_kb("owner", "公司库", scope="company")
    kbs = await kb_service.list_accessible_kbs("member", is_admin=False, dept_id=None)
    assert "公司库" in {k["name"] for k in kbs}


async def test_admin_sees_all(sqlite_db):
    await kb_service.create_kb("owner", "d1库", scope="dept", dept_id="d1")
    await kb_service.create_kb("owner", "admin库", scope="admin")
    kbs = await kb_service.list_accessible_kbs("boss", is_admin=True)
    assert {"d1库", "admin库"} <= {k["name"] for k in kbs}


# ── DB 集成：check_permission 部门规则 ────────────────────────────────────────

async def test_super_admin_full_access(sqlite_db):
    r = await kb_service.create_kb("owner", "admin库", scope="admin")
    assert await kb_service.check_permission(
        "anyone", r["kb_id"], "admin", is_admin=True) is True


async def test_dept_member_read_only(sqlite_db):
    r = await kb_service.create_kb("owner", "d1库", scope="dept", dept_id="d1")
    kb_id = r["kb_id"]
    assert await kb_service.check_permission("m", kb_id, "viewer", dept_id="d1") is True
    assert await kb_service.check_permission("m", kb_id, "editor", dept_id="d1") is False


async def test_dept_admin_manage(sqlite_db):
    r = await kb_service.create_kb("owner", "d1库", scope="dept", dept_id="d1")
    assert await kb_service.check_permission(
        "da", r["kb_id"], "admin", dept_id="d1", is_dept_admin=True) is True


async def test_other_dept_denied(sqlite_db):
    r = await kb_service.create_kb("owner", "d1库", scope="dept", dept_id="d1")
    assert await kb_service.check_permission(
        "m2", r["kb_id"], "viewer", dept_id="d2", is_dept_admin=True) is False


# ── DB 集成：handle_create_kb 写权限接线 ──────────────────────────────────────

from fastapi import HTTPException  # noqa: E402

from app.router.chat_service import ChatService  # noqa: E402
from app.utils.auth_utils import RequestIdentity  # noqa: E402


async def test_handle_create_company_kb_denied_for_member(sqlite_db):
    """修复点：普通成员不能再建 company 库"""
    svc = ChatService()
    member = RequestIdentity(user_id="m", is_admin=False, dept_id="d1", is_dept_admin=False)
    with pytest.raises(HTTPException) as exc:
        await svc.handle_create_kb(member, "公司库", "company", None, "")
    assert exc.value.status_code == 403


async def test_handle_create_dept_kb_by_dept_admin(sqlite_db):
    """部门管理员建本部门库，dept_id 回填为自身部门"""
    svc = ChatService()
    da = RequestIdentity(user_id="da", is_admin=False, dept_id="d1", is_dept_admin=True)
    kb = await svc.handle_create_kb(da, "研发库", "dept", None, "")
    stored = await kb_service.get_kb(kb["kb_id"])
    assert stored.scope == "dept" and stored.dept_id == "d1"
