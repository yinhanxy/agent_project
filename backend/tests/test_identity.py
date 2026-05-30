from app.utils.auth_utils import RequestIdentity, build_identity


def test_build_identity_full_fields():
    info = {"is_admin": True, "dept_id": "d1", "is_dept_admin": True}
    idy = build_identity("u1", info)
    assert idy == RequestIdentity(user_id="u1", is_admin=True, dept_id="d1", is_dept_admin=True)


def test_build_identity_degrades_on_missing_fields():
    """缺字段降级为：无部门 + 普通成员"""
    idy = build_identity("u1", {})
    assert idy.user_id == "u1"
    assert idy.is_admin is False
    assert idy.dept_id is None
    assert idy.is_dept_admin is False


def test_build_identity_none_user_info():
    idy = build_identity("u1", None)
    assert idy.user_id == "u1" and idy.dept_id is None and idy.is_admin is False


def test_build_identity_blank_dept_normalized_to_none():
    assert build_identity("u1", {"dept_id": ""}).dept_id is None
