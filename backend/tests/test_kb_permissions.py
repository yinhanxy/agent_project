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
