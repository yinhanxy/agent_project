# 部门权限 Phase 1（Django 部门体系）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Django 账号服务（`DjangoUserService/`）中落地部门组织结构与角色，使 `user_info`/用户列表接口返回 `dept_id`/`dept_name`/`is_dept_admin`，并提供部门 CRUD、分配账号部门、任命部门管理员的管理接口（仅总管理员可操作）。

**Architecture:** 新增 `Department` 模型，`User` 增加 `dept`(FK) 与 `is_dept_admin`。`get_user_info()`（被 `@cache_user_info()` 缓存到 Redis，是 FastAPI 取用户信息的源头）与 `UserListView` 补返回部门字段。新增管理接口沿用现有 `UserSetAdminView` 的「仅 `is_admin` 可操作 + 改完 `clear_user_cache`」模式。

**Tech Stack:** Django + DRF，自定义 `User`（`AbstractBaseUser`，`db_table='user_service'`，主键 `ShortUUIDField`），JWT 自实现（`authentications.py`），测试用 Django `TestCase` + DRF `APIClient`，`manage.py test` 运行。

**约定（每个 Task 通用）：**
- 工作目录：`DjangoUserService/`
- 运行测试：`python manage.py test apps.user.tests -v 2`（用该服务的 Python 环境）
- 该服务连 MySQL，跑测试需 DB 账号有创建 `test_*` 库的权限

---

## 文件结构

| 文件 | 职责 | 动作 |
|------|------|------|
| `DjangoUserService/apps/user/models.py` | `Department` 模型 + `User.dept`/`is_dept_admin` | 修改 |
| `DjangoUserService/apps/user/migrations/000X_*.py` | 数据库迁移 | 生成 |
| `DjangoUserService/apps/user/views.py` | `get_user_info` 补字段、`UserListView` 补字段、新增部门/分配/任命视图 | 修改 |
| `DjangoUserService/apps/user/urls.py` | 注册新路由 | 修改 |
| `DjangoUserService/apps/user/tests.py` | 全部测试 | 修改 |

---

## Task 1: Department 模型与 User 部门字段

**Files:**
- Modify: `DjangoUserService/apps/user/models.py`
- Test: `DjangoUserService/apps/user/tests.py`

- [ ] **Step 1: 写失败测试**

替换 `apps/user/tests.py` 全部内容为：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python manage.py test apps.user.tests.DepartmentModelTest -v 2`
Expected: FAIL — `ImportError: cannot import name 'Department'`

- [ ] **Step 3: 写模型实现**

在 `apps/user/models.py` 中，`UserManager` 类定义之后、`class User` 之前，新增 `Department` 模型：

```python
class Department(models.Model):
    """部门"""
    dept_id = ShortUUIDField(primary_key=True, unique=True, editable=False)
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'department'

    def __str__(self):
        return self.name
```

在 `class User(AbstractBaseUser)` 内，`avatar` 字段之后新增两个字段：

```python
    # 所属部门（单部门归属，可为空）
    dept = models.ForeignKey(
        'Department', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='members',
    )
    # 是否本部门管理员（总管理员任命）
    is_dept_admin = models.BooleanField(default=False)
```

- [ ] **Step 4: 生成并执行迁移**

Run: `python manage.py makemigrations user`
Expected: 生成 `apps/user/migrations/000X_department_user_dept_user_is_dept_admin.py`（含 `CreateModel Department` 与 `AddField dept/is_dept_admin`）

Run: `python manage.py migrate`
Expected: `Applying user.000X... OK`

- [ ] **Step 5: 运行测试确认通过**

Run: `python manage.py test apps.user.tests.DepartmentModelTest -v 2`
Expected: PASS（3 个测试）

- [ ] **Step 6: 提交**

```bash
git add DjangoUserService/apps/user/models.py DjangoUserService/apps/user/migrations/ DjangoUserService/apps/user/tests.py
git commit -m "feat(django): 新增 Department 模型与 User 部门字段"
```

---

## Task 2: user_info / detail 接口返回部门字段

`get_user_info()`（`views.py:217`）是 FastAPI 经 Redis 读取用户信息的源头，必须补部门字段。

**Files:**
- Modify: `DjangoUserService/apps/user/views.py:217-231`
- Test: `DjangoUserService/apps/user/tests.py`

- [ ] **Step 1: 写失败测试**

在 `apps/user/tests.py` 末尾追加（顶部 import 增加 `from rest_framework.test import APIClient`、`from apps.user.authentications import JWTTokenGenerator`）：

```python
from rest_framework.test import APIClient
from apps.user.authentications import JWTTokenGenerator


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
```

> 路由前缀确认：`apps/user/urls.py` 的 `detail/` 在项目根 `urls.py` 下的挂载前缀以实际为准；若不是 `/user/`，把测试里的路径改成实际前缀。

- [ ] **Step 2: 运行测试确认失败**

Run: `python manage.py test apps.user.tests.UserDetailDeptTest -v 2`
Expected: FAIL — `KeyError: 'dept_id'`

- [ ] **Step 3: 写实现**

把 `views.py` 中 `get_user_info` 函数体替换为：

```python
@cache_user_info()
def get_user_info(user):
    serializer = UserSerializer(user)
    return {
        "id": serializer.data.get('uuid'),
        "username": serializer.data.get('username'),
        "email": serializer.data.get('email'),
        "avatar": serializer.data.get('avatar'),
        "telephone": serializer.data.get('telephone'),
        "gender": serializer.data.get('gender'),
        "bio": serializer.data.get('bio'),
        "is_admin": serializer.data.get('is_admin', False),
        "dept_id": str(user.dept_id) if user.dept_id else None,
        "dept_name": user.dept.name if user.dept_id else None,
        "is_dept_admin": getattr(user, 'is_dept_admin', False),
        "create_time": serializer.data.get('date_joined'),
        "last_login": serializer.data.get('last_login'),
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python manage.py test apps.user.tests.UserDetailDeptTest -v 2`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add DjangoUserService/apps/user/views.py DjangoUserService/apps/user/tests.py
git commit -m "feat(django): user_info 返回 dept_id/dept_name/is_dept_admin"
```

---

## Task 3: 用户列表接口返回部门字段

前端账号管理页用 `/user/list/` 展示账号，需带部门信息。

**Files:**
- Modify: `DjangoUserService/apps/user/views.py:324-343`（`UserListView.get`）
- Test: `DjangoUserService/apps/user/tests.py`

- [ ] **Step 1: 写失败测试**

在 `tests.py` 末尾追加：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python manage.py test apps.user.tests.UserListDeptTest -v 2`
Expected: FAIL — `KeyError: 'dept_id'`

- [ ] **Step 3: 写实现**

把 `UserListView.get` 里构造 `data.append({...})` 的循环替换为（用 `select_related('dept')` 避免 N+1）：

```python
    def get(self, request) -> Response:
        if not getattr(request.user, 'is_admin', False):
            return Response({"detail": "无权限"}, status=status.HTTP_403_FORBIDDEN)
        users = User.objects.select_related('dept').all().order_by('date_joined')
        data = []
        for u in users:
            data.append({
                "uuid": str(u.uuid),
                "username": u.username,
                "email": u.email,
                "telephone": u.telephone,
                "is_admin": u.is_admin,
                "dept_id": str(u.dept_id) if u.dept_id else None,
                "dept_name": u.dept.name if u.dept_id else None,
                "is_dept_admin": u.is_dept_admin,
                "status": u.status,
                "date_joined": u.date_joined.isoformat() if u.date_joined else None,
                "last_login": u.last_login.isoformat() if u.last_login else None,
            })
        return Response({"users": data, "total": len(data)}, status=status.HTTP_200_OK)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python manage.py test apps.user.tests.UserListDeptTest -v 2`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add DjangoUserService/apps/user/views.py DjangoUserService/apps/user/tests.py
git commit -m "feat(django): 用户列表返回部门字段"
```

---

## Task 4: 部门 CRUD 接口（仅总管理员）

**Files:**
- Modify: `DjangoUserService/apps/user/views.py`（新增视图）、`DjangoUserService/apps/user/urls.py`
- Test: `DjangoUserService/apps/user/tests.py`

- [ ] **Step 1: 写失败测试**

在 `tests.py` 末尾追加：

```python
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

    def test_admin_can_delete_department(self):
        dept = Department.objects.create(name="待删部门")
        resp = _auth_client(self.admin).delete(f"/user/departments/{dept.dept_id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Department.objects.filter(dept_id=dept.dept_id).exists())
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python manage.py test apps.user.tests.DepartmentApiTest -v 2`
Expected: FAIL — 404（路由不存在）

- [ ] **Step 3: 写视图实现**

在 `views.py` 中导入区下方新增 `Department` 导入：把 `from .models import User` 改为 `from .models import User, Department`。

在 `UserSetAdminView` 之后新增两个视图：

```python
class DepartmentListCreateView(AuthenticatedView):
    """部门列表与创建（仅总管理员可创建）"""

    def get(self, request) -> Response:
        depts = Department.objects.all().order_by('created_at')
        data = [{"dept_id": str(d.dept_id), "name": d.name} for d in depts]
        return Response({"departments": data, "total": len(data)}, status=status.HTTP_200_OK)

    def post(self, request) -> Response:
        if not getattr(request.user, 'is_admin', False):
            return Response({"detail": "无权限"}, status=status.HTTP_403_FORBIDDEN)
        name = (request.data.get('name') or '').strip()
        if not name:
            return Response({"detail": "部门名称不能为空"}, status=status.HTTP_400_BAD_REQUEST)
        if Department.objects.filter(name=name).exists():
            return Response({"detail": "部门名称已存在"}, status=status.HTTP_400_BAD_REQUEST)
        dept = Department.objects.create(name=name)
        return Response({"dept_id": str(dept.dept_id), "name": dept.name}, status=status.HTTP_201_CREATED)


class DepartmentDetailView(AuthenticatedView):
    """部门改名 / 删除（仅总管理员）"""

    def patch(self, request, dept_id) -> Response:
        if not getattr(request.user, 'is_admin', False):
            return Response({"detail": "无权限"}, status=status.HTTP_403_FORBIDDEN)
        try:
            dept = Department.objects.get(dept_id=dept_id)
        except Department.DoesNotExist:
            return Response({"detail": "部门不存在"}, status=status.HTTP_404_NOT_FOUND)
        name = (request.data.get('name') or '').strip()
        if not name:
            return Response({"detail": "部门名称不能为空"}, status=status.HTTP_400_BAD_REQUEST)
        dept.name = name
        dept.save()
        return Response({"dept_id": str(dept.dept_id), "name": dept.name}, status=status.HTTP_200_OK)

    def delete(self, request, dept_id) -> Response:
        if not getattr(request.user, 'is_admin', False):
            return Response({"detail": "无权限"}, status=status.HTTP_403_FORBIDDEN)
        try:
            dept = Department.objects.get(dept_id=dept_id)
        except Department.DoesNotExist:
            return Response({"detail": "部门不存在"}, status=status.HTTP_404_NOT_FOUND)
        dept.delete()  # User.dept 为 SET_NULL，成员自动解除归属
        return Response({"detail": "部门已删除"}, status=status.HTTP_200_OK)
```

- [ ] **Step 4: 注册路由**

在 `urls.py` 的 import 中加入新视图名，并在 `urlpatterns` 末尾新增：

```python
    path('departments/', DepartmentListCreateView.as_view(), name='dept-list-create'),
    path('departments/<str:dept_id>/', DepartmentDetailView.as_view(), name='dept-detail'),
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python manage.py test apps.user.tests.DepartmentApiTest -v 2`
Expected: PASS（3 个测试）

- [ ] **Step 6: 提交**

```bash
git add DjangoUserService/apps/user/views.py DjangoUserService/apps/user/urls.py DjangoUserService/apps/user/tests.py
git commit -m "feat(django): 部门 CRUD 接口（仅总管理员）"
```

---

## Task 5: 分配账号部门接口（仅总管理员）

**Files:**
- Modify: `DjangoUserService/apps/user/views.py`、`DjangoUserService/apps/user/urls.py`
- Test: `DjangoUserService/apps/user/tests.py`

- [ ] **Step 1: 写失败测试**

在 `tests.py` 末尾追加：

```python
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
        self.member.save()
        resp = _auth_client(self.admin).patch(
            f"/user/{self.member.uuid}/set-dept/",
            {"dept_id": None}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.member.refresh_from_db()
        self.assertIsNone(self.member.dept_id)

    def test_member_cannot_assign_department(self):
        resp = _auth_client(self.member).patch(
            f"/user/{self.member.uuid}/set-dept/",
            {"dept_id": str(self.dept.dept_id)}, format="json")
        self.assertEqual(resp.status_code, 403)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python manage.py test apps.user.tests.SetDeptApiTest -v 2`
Expected: FAIL — 404

- [ ] **Step 3: 写视图实现**

在 `views.py` 的 `DepartmentDetailView` 之后新增（顶部确保已导入 `clear_user_cache`，现有已导入）：

```python
class UserSetDeptView(AuthenticatedView):
    """总管理员：设置某用户所属部门（dept_id 传 null 表示移出部门）"""

    def patch(self, request, uuid) -> Response:
        if not getattr(request.user, 'is_admin', False):
            return Response({"detail": "无权限"}, status=status.HTTP_403_FORBIDDEN)
        try:
            target = User.objects.get(uuid=uuid)
        except User.DoesNotExist:
            return Response({"detail": "用户不存在"}, status=status.HTTP_404_NOT_FOUND)

        dept_id = request.data.get('dept_id')
        if dept_id in (None, "", "null"):
            target.dept = None
            target.is_dept_admin = False  # 移出部门同时清掉部门管理员身份
        else:
            try:
                target.dept = Department.objects.get(dept_id=dept_id)
            except Department.DoesNotExist:
                return Response({"detail": "部门不存在"}, status=status.HTTP_404_NOT_FOUND)
        target.save()
        clear_user_cache(target.uuid)
        return Response({
            "uuid": str(target.uuid),
            "dept_id": str(target.dept_id) if target.dept_id else None,
        }, status=status.HTTP_200_OK)
```

- [ ] **Step 4: 注册路由**

在 `urls.py` import 加入 `UserSetDeptView`，`urlpatterns` 末尾新增：

```python
    path('<str:uuid>/set-dept/', UserSetDeptView.as_view(), name='user-set-dept'),
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python manage.py test apps.user.tests.SetDeptApiTest -v 2`
Expected: PASS（3 个测试）

- [ ] **Step 6: 提交**

```bash
git add DjangoUserService/apps/user/views.py DjangoUserService/apps/user/urls.py DjangoUserService/apps/user/tests.py
git commit -m "feat(django): 分配账号部门接口（仅总管理员）"
```

---

## Task 6: 任命部门管理员接口（仅总管理员）

**Files:**
- Modify: `DjangoUserService/apps/user/views.py`、`DjangoUserService/apps/user/urls.py`
- Test: `DjangoUserService/apps/user/tests.py`

- [ ] **Step 1: 写失败测试**

在 `tests.py` 末尾追加：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python manage.py test apps.user.tests.SetDeptAdminApiTest -v 2`
Expected: FAIL — 404

- [ ] **Step 3: 写视图实现**

在 `views.py` 的 `UserSetDeptView` 之后新增：

```python
class UserSetDeptAdminView(AuthenticatedView):
    """总管理员：设置/取消某用户的部门管理员身份（须先归属某部门）"""

    def patch(self, request, uuid) -> Response:
        if not getattr(request.user, 'is_admin', False):
            return Response({"detail": "无权限"}, status=status.HTTP_403_FORBIDDEN)
        try:
            target = User.objects.get(uuid=uuid)
        except User.DoesNotExist:
            return Response({"detail": "用户不存在"}, status=status.HTTP_404_NOT_FOUND)

        is_dept_admin = bool(request.data.get('is_dept_admin'))
        if is_dept_admin and not target.dept_id:
            return Response({"detail": "该用户尚未归属任何部门，无法任命为部门管理员"},
                            status=status.HTTP_400_BAD_REQUEST)
        target.is_dept_admin = is_dept_admin
        target.save()
        clear_user_cache(target.uuid)
        return Response({
            "uuid": str(target.uuid),
            "is_dept_admin": target.is_dept_admin,
        }, status=status.HTTP_200_OK)
```

- [ ] **Step 4: 注册路由**

在 `urls.py` import 加入 `UserSetDeptAdminView`，`urlpatterns` 末尾新增：

```python
    path('<str:uuid>/set-dept-admin/', UserSetDeptAdminView.as_view(), name='user-set-dept-admin'),
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python manage.py test apps.user.tests.SetDeptAdminApiTest -v 2`
Expected: PASS（3 个测试）

- [ ] **Step 6: 全量回归 + 提交**

Run: `python manage.py test apps.user.tests -v 2`
Expected: 全部 PASS

```bash
git add DjangoUserService/apps/user/views.py DjangoUserService/apps/user/urls.py DjangoUserService/apps/user/tests.py
git commit -m "feat(django): 任命部门管理员接口（仅总管理员）"
```

---

## Phase 1 验收标准

- `Department` 表与 `User.dept`/`is_dept_admin` 已迁移
- `/user/detail/` 与 `/user/list/` 返回 `dept_id`/`dept_name`/`is_dept_admin`（FastAPI 据此读取，对接契约达成）
- 总管理员可：建/改/删部门、给账号分配部门、任命部门管理员；普通成员调用上述写接口一律 403
- 改部门/管理员身份后清除 Redis 用户缓存（`clear_user_cache`），下次取 `user_info` 即新值
- `python manage.py test apps.user.tests` 全绿

## Phase 1 完成后

接口契约（`dept_id`/`dept_name`/`is_dept_admin`）已就绪，方可进入：
- **Phase 2（FastAPI）**：消费身份 + 知识库部门隔离 + 写权限校验 + 补 `/rag/query` 过滤 + 删死代码
- **Phase 3（前端）**：账号管理部门分配界面 + 知识库页角色化
