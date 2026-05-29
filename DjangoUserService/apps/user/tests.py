from django.test import TestCase
from apps.user.models import User, Department, UserStatusChoice


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
