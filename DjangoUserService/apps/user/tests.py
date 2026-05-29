from django.test import TestCase
from apps.user.models import User, Department, UserStatusChoice
from rest_framework.test import APIClient
from apps.user.authentications import JWTTokenGenerator


class DepartmentModelTest(TestCase):
    def test_create_department(self):
        dept = Department.objects.create(name="研发部")
        self.assertEqual(dept.name, "研发部")
        self.assertTrue(dept.dept_id)  # ShortUUID 自动生成

    def test_user_belongs_to_one_department(self):
        dept = Department.objects.create(name="研发部")
        user = User.objects.create_user(
            username="u1", email="u1@example.com", password="pass123",
            status=UserStatusChoice.ACTIVE, dept=dept,
        )
        self.assertEqual(user.dept.name, "研发部")
        self.assertFalse(user.is_dept_admin)  # 默认非部门管理员

    def test_user_dept_nullable(self):
        user = User.objects.create_user(
            username="u2", email="u2@example.com", password="pass123",
            status=UserStatusChoice.ACTIVE,
        )
        self.assertIsNone(user.dept_id)


def _auth_client(user):
    client = APIClient()
    token, _ = JWTTokenGenerator().generate_token(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


class UserDetailDeptTest(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name="研发部")
        self.user = User.objects.create_user(
            username="u1", email="u1@example.com", password="pass123",
            status=UserStatusChoice.ACTIVE, dept=self.dept, is_dept_admin=True,
        )

    def test_detail_returns_department_fields(self):
        resp = _auth_client(self.user).get("/user/detail/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["dept_id"], str(self.dept.dept_id))
        self.assertEqual(data["dept_name"], "研发部")
        self.assertTrue(data["is_dept_admin"])


class UserListDeptTest(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name="研发部")
        self.admin = User.objects.create_user(
            username="admin", email="admin@example.com", password="pass123",
            status=UserStatusChoice.ACTIVE, is_admin=True,
        )
        self.member = User.objects.create_user(
            username="m1", email="m1@example.com", password="pass123",
            status=UserStatusChoice.ACTIVE, dept=self.dept, is_dept_admin=True,
        )

    def test_list_includes_dept_fields(self):
        resp = _auth_client(self.admin).get("/user/list/")
        self.assertEqual(resp.status_code, 200)
        users = resp.json()["users"]
        target = next(u for u in users if u["username"] == "m1")
        self.assertEqual(target["dept_id"], str(self.dept.dept_id))
        self.assertEqual(target["dept_name"], "研发部")
        self.assertTrue(target["is_dept_admin"])


class DepartmentApiTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin", email="admin@example.com", password="pass123",
            status=UserStatusChoice.ACTIVE, is_admin=True,
        )
        self.member = User.objects.create_user(
            username="m1", email="m1@example.com", password="pass123",
            status=UserStatusChoice.ACTIVE,
        )

    def test_admin_can_create_and_list_department(self):
        c = _auth_client(self.admin)
        resp = c.post("/user/departments/", {"name": "市场部"}, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["name"], "市场部")
        resp = c.get("/user/departments/")
        self.assertEqual(resp.status_code, 200)
        names = [d["name"] for d in resp.json()["departments"]]
        self.assertIn("市场部", names)

    def test_member_cannot_create_department(self):
        resp = _auth_client(self.member).post(
            "/user/departments/", {"name": "市场部"}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_member_cannot_list_department(self):
        resp = _auth_client(self.member).get("/user/departments/")
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_delete_department(self):
        dept = Department.objects.create(name="待删部门")
        resp = _auth_client(self.admin).delete(f"/user/departments/{dept.dept_id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Department.objects.filter(dept_id=dept.dept_id).exists())


class SetDeptApiTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin", email="admin@example.com", password="pass123",
            status=UserStatusChoice.ACTIVE, is_admin=True,
        )
        self.member = User.objects.create_user(
            username="m1", email="m1@example.com", password="pass123",
            status=UserStatusChoice.ACTIVE,
        )
        self.dept = Department.objects.create(name="研发部")

    def test_admin_assigns_user_to_department(self):
        resp = _auth_client(self.admin).patch(
            f"/user/{self.member.uuid}/set-dept/",
            {"dept_id": str(self.dept.dept_id)}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.member.refresh_from_db()
        self.assertEqual(self.member.dept_id, self.dept.dept_id)

    def test_assign_null_clears_department(self):
        self.member.dept = self.dept
        self.member.is_dept_admin = True
        self.member.save()
        resp = _auth_client(self.admin).patch(
            f"/user/{self.member.uuid}/set-dept/",
            {"dept_id": None}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.member.refresh_from_db()
        self.assertIsNone(self.member.dept_id)
        self.assertFalse(self.member.is_dept_admin)

    def test_member_cannot_assign_department(self):
        resp = _auth_client(self.member).patch(
            f"/user/{self.member.uuid}/set-dept/",
            {"dept_id": str(self.dept.dept_id)}, format="json")
        self.assertEqual(resp.status_code, 403)


class SetDeptAdminApiTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin", email="admin@example.com", password="pass123",
            status=UserStatusChoice.ACTIVE, is_admin=True,
        )
        self.dept = Department.objects.create(name="研发部")
        self.member = User.objects.create_user(
            username="m1", email="m1@example.com", password="pass123",
            status=UserStatusChoice.ACTIVE, dept=self.dept,
        )
        self.nodept = User.objects.create_user(
            username="m2", email="m2@example.com", password="pass123",
            status=UserStatusChoice.ACTIVE,
        )

    def test_admin_appoints_dept_admin(self):
        resp = _auth_client(self.admin).patch(
            f"/user/{self.member.uuid}/set-dept-admin/",
            {"is_dept_admin": True}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_dept_admin)

    def test_cannot_appoint_user_without_department(self):
        resp = _auth_client(self.admin).patch(
            f"/user/{self.nodept.uuid}/set-dept-admin/",
            {"is_dept_admin": True}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_member_cannot_appoint(self):
        resp = _auth_client(self.member).patch(
            f"/user/{self.member.uuid}/set-dept-admin/",
            {"is_dept_admin": True}, format="json")
        self.assertEqual(resp.status_code, 403)
