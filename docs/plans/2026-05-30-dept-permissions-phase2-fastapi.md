# 部门权限 Phase 2（FastAPI 知识库隔离）实现计划

> **For agentic workers:** 用 TDD 逐 Task 实现。每个 Task 先写失败测试 → 跑红 → 写实现 → 跑绿 → 提交。

**Goal:** 让 FastAPI 知识库服务真正消费 Django 下发的部门身份（`dept_id`/`is_dept_admin`），实现「部门内共享、部门间隔离」的知识库可见性与写权限校验，补全 `/rag/query` 的用户过滤，删除遗留死代码，并新增供前端账号管理使用的部门管理代理端点。

**Architecture:**
- `auth_utils` 新增 `RequestIdentity`（`user_id`/`is_admin`/`dept_id`/`is_dept_admin`）与依赖 `get_current_identity`，从 Redis 缓存的 `user_info` 提取并打包。
- 身份沿 `query_stream 路由 → get_agent_stream_response → AgentLoop.stream → _execute_tool → rag_summary_tools → _build_rag_filter` 显式传递（不走 ContextVar，延续上次 citations 修复原则）。
- 权限判定下沉为**纯函数**（`can_create_kb`、`assemble_rag_filter`）便于单元测试；DB 可见性（`list_accessible_kbs`、`check_permission`）补部门规则，用 SQLite 内存库做集成测试。
- 部门管理端点沿用现有 `/api/admin/users` 代理模式（`is_admin` 网关 + `proxies={http:None,https:None}` 清代理 + `run_in_executor`）转发到 Django。

**Tech Stack:** FastAPI + SQLAlchemy 2.0（async）+ pytest（`asyncio_mode=auto`）。测试目录 `backend/tests/`，运行 `backend/.venv/Scripts/python.exe -m pytest`。DB 集成测试需 `aiosqlite`（纯测试依赖，执行时 `pip install aiosqlite`）。

**约定（每个 Task 通用）：**
- 工作目录：worktree `backend/`
- 运行测试：`backend/.venv/Scripts/python.exe -m pytest tests/ -v`
- FastAPI 调 Django 一律带 `proxies={"http": None, "https": None}`，避免本地 127.0.0.1 请求被系统代理拦截导致 ReadTimeout

---

## 文件结构

| 文件 | 职责 | 动作 |
|------|------|------|
| `backend/app/utils/auth_utils.py` | `RequestIdentity` + `build_identity` + `get_current_identity` | 修改 |
| `backend/app/services/kb_service.py` | `list_accessible_kbs` 纳入本部门库、`check_permission` 补部门规则、`can_create_kb`/`assemble_rag_filter`/`build_accessible_filter` | 修改 |
| `backend/app/agent/agent_tools.py` | `_build_rag_filter`/`rag_summary_tools` 改收身份对象 | 修改 |
| `backend/app/agent/agent.py` | `stream`/`_execute_tool` 传身份；删 `run`/`get_agent_response` | 修改 |
| `backend/app/router/chat_service.py` | KB 写权限校验、`/rag/query` 过滤、删 `handle_agent_query` | 修改 |
| `backend/app/router/chat.py` | KB 路由注入身份、`/rag/query` 注入身份、新增部门代理端点 | 修改 |
| `backend/tests/conftest.py` | SQLite 内存库 fixture（patch `AsyncSessionLocal`） | 新增 |
| `backend/tests/test_identity.py` | 身份提取单元测试 | 新增 |
| `backend/tests/test_kb_permissions.py` | 纯函数 + DB 集成测试 | 新增 |

---

## Task 1: RequestIdentity 与身份提取（auth_utils）

**Files:** Modify `app/utils/auth_utils.py`；Test `tests/test_identity.py`

- [ ] **Step 1: 失败测试** — `tests/test_identity.py`：

```python
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
```

- [ ] **Step 2: 跑红** — `pytest tests/test_identity.py -v` → ImportError

- [ ] **Step 3: 实现** — `auth_utils.py` 顶部加 `from dataclasses import dataclass`，在 `get_current_user_is_admin` 之后新增：

```python
@dataclass(frozen=True)
class RequestIdentity:
    """请求级身份：知识库权限判定的统一输入。"""
    user_id: str
    is_admin: bool = False
    dept_id: Optional[str] = None
    is_dept_admin: bool = False


def build_identity(user_id: str, user_info: Optional[Dict[str, Any]]) -> RequestIdentity:
    """从 user_info 提取身份；缺字段降级为「无部门 + 普通成员」。"""
    info = user_info if isinstance(user_info, dict) else {}
    dept_id = info.get("dept_id") or None  # "" / None 统一成 None
    return RequestIdentity(
        user_id=user_id,
        is_admin=bool(info.get("is_admin", False)),
        dept_id=dept_id,
        is_dept_admin=bool(info.get("is_dept_admin", False)),
    )


async def get_current_identity(
    user_id: str = Depends(get_current_user_id),
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> RequestIdentity:
    """FastAPI 依赖：解析当前请求的部门身份。"""
    try:
        user_info = await get_user_info_from_redis(user_id, credentials)
    except Exception as e:
        logger.error(f"[identity] 取用户信息失败，降级为普通成员: {e}",
                     extra={"path": "auth_utils.get_current_identity"})
        user_info = None
    return build_identity(user_id, user_info)
```

- [ ] **Step 4: 跑绿** — `pytest tests/test_identity.py -v` → 4 passed

- [ ] **Step 5: 提交** — `git add backend/app/utils/auth_utils.py backend/tests/test_identity.py` → `feat(fastapi): 新增 RequestIdentity 与部门身份提取依赖`

---

## Task 2: KB 创建写权限纯函数 `can_create_kb`

修掉现有漏洞：`handle_create_kb` 的 `if not is_admin and scope in ("dept","admin")` 漏了 `company`（普通用户当前可建 company 库）；并加入部门管理员可建本部门 `dept` 库。

**Files:** Modify `app/services/kb_service.py`；Test `tests/test_kb_permissions.py`

- [ ] **Step 1: 失败测试** — 新建 `tests/test_kb_permissions.py`：

```python
import pytest
from app.services.kb_service import can_create_kb


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
```

- [ ] **Step 2: 跑红** — ImportError

- [ ] **Step 3: 实现** — `kb_service.py` 模块级（`_ROLE_RANK` 之后）新增纯函数：

```python
def can_create_kb(
    scope: str,
    is_admin: bool,
    is_dept_admin: bool,
    user_dept_id: Optional[str],
    req_dept_id: Optional[str],
) -> tuple[bool, Optional[str]]:
    """返回 (是否允许, 生效的 dept_id)。纯函数，无副作用。"""
    if scope == "personal":
        return True, None
    if scope in ("company", "admin"):
        return (True, None) if is_admin else (False, None)
    if scope == "dept":
        if is_admin:
            return True, (req_dept_id or None)
        if is_dept_admin and user_dept_id and req_dept_id in (None, "", user_dept_id):
            return True, user_dept_id
        return False, None
    return False, None
```

- [ ] **Step 4: 跑绿** — `pytest tests/test_kb_permissions.py -v`

- [ ] **Step 5: 提交** — `feat(fastapi): KB 创建写权限纯函数 can_create_kb（修 company 漏洞 + 部门管理员建本部门库）`

---

## Task 3: RAG 过滤纯函数 `assemble_rag_filter`

集中过滤条件组装，agent 路径与 `/rag/query` 复用。

**Files:** Modify `app/services/kb_service.py`；Test 追加到 `tests/test_kb_permissions.py`

- [ ] **Step 1: 失败测试** — 追加：

```python
from app.services.kb_service import assemble_rag_filter


def test_filter_admin_no_filter():
    assert assemble_rag_filter("u1", is_admin=True, accessible_kb_ids=["k1"]) is None


def test_filter_no_user_id_returns_none():
    assert assemble_rag_filter("", is_admin=False, accessible_kb_ids=["k1"]) is None


def test_filter_with_kb_ids():
    f = assemble_rag_filter("u1", False, ["k1", "k2"])
    assert f == {"$or": [{"user_id": {"$eq": "u1"}}, {"kb_id": {"$in": ["k1", "k2"]}}]}


def test_filter_without_kb_ids_personal_only():
    assert assemble_rag_filter("u1", False, []) == {"user_id": {"$eq": "u1"}}
```

- [ ] **Step 2: 跑红**

- [ ] **Step 3: 实现** — `kb_service.py` 模块级新增：

```python
def assemble_rag_filter(
    user_id: str, is_admin: bool, accessible_kb_ids: List[str]
) -> Optional[dict]:
    """组装向量库/BM25 过滤条件。
    管理员 → None（全库可见）；无 user_id → None（调用方负责告警）。
    """
    if is_admin:
        return None
    if not user_id:
        return None
    if accessible_kb_ids:
        return {
            "$or": [
                {"user_id": {"$eq": user_id}},
                {"kb_id": {"$in": accessible_kb_ids}},
            ]
        }
    return {"user_id": {"$eq": user_id}}
```

并在 `KBService` 内新增异步便捷方法（拼装 DB 查询 + 纯函数）：

```python
    async def build_accessible_filter(
        self, user_id: str, is_admin: bool = False, dept_id: Optional[str] = None
    ) -> Optional[dict]:
        if is_admin or not user_id:
            return assemble_rag_filter(user_id, is_admin, [])
        ids = await self.get_accessible_kb_ids(user_id, is_admin=is_admin, dept_id=dept_id)
        return assemble_rag_filter(user_id, is_admin, ids)
```

- [ ] **Step 4: 跑绿**

- [ ] **Step 5: 提交** — `feat(fastapi): 集中式 RAG 过滤组装 assemble_rag_filter/build_accessible_filter`

---

## Task 4: list_accessible_kbs 纳入本部门 dept 库（DB 集成）

**Files:** `tests/conftest.py`（新增）、`app/services/kb_service.py`；Test 追加到 `tests/test_kb_permissions.py`

- [ ] **Step 1: conftest fixture** — 新建 `tests/conftest.py`：

```python
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.models.chat_history import Base


@pytest_asyncio.fixture
async def sqlite_db(monkeypatch):
    """用 SQLite 内存库替换 kb_service 的 AsyncSessionLocal。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    import app.services.kb_service as kb_mod
    monkeypatch.setattr(kb_mod, "AsyncSessionLocal", Session)
    yield Session
    await engine.dispose()
```

> 顶部 `tests/test_kb_permissions.py` 加 `pytest.importorskip("aiosqlite")`，未装 aiosqlite 时自动跳过 DB 测试（纯函数测试不受影响）。

- [ ] **Step 2: 失败测试** — 追加：

```python
pytest.importorskip("aiosqlite")
from app.services.kb_service import kb_service


async def test_dept_member_sees_own_dept_kb(sqlite_db):
    # d1 部门库 + d2 部门库 + 个人库
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
```

- [ ] **Step 3: 跑红** — `test_dept_member_sees_own_dept_kb` 失败（本部门库未纳入）

- [ ] **Step 4: 实现** — `list_accessible_kbs` 非管理员分支，把最终 `KnowledgeBase` 查询的 `or_(...)` 补一条本部门 dept 条件：

```python
                dept_clause = or_(
                    KnowledgeBase.kb_id.in_(granted_kb_ids),
                    KnowledgeBase.scope == "company",
                )
                if dept_id:
                    dept_clause = or_(
                        dept_clause,
                        and_(
                            KnowledgeBase.scope == "dept",
                            KnowledgeBase.dept_id == dept_id,
                        ),
                    )
                rows = (await db.execute(
                    select(KnowledgeBase).where(
                        and_(KnowledgeBase.scope != "admin", dept_clause)
                    )
                )).scalars().all()
```

- [ ] **Step 5: 跑绿**

- [ ] **Step 6: 提交** — `feat(fastapi): list_accessible_kbs 纳入本部门 dept 库（部门内共享）`

---

## Task 5: check_permission 补部门规则（DB 集成）

部门库：本部门成员只读（viewer）、本部门管理员可管（admin）、他部门拒绝；总管理员全权。

**Files:** `app/services/kb_service.py`；Test 追加

- [ ] **Step 1: 失败测试** — 追加：

```python
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
```

- [ ] **Step 2: 跑红**

- [ ] **Step 3: 实现** — `check_permission` 签名扩展为
`check_permission(self, user_id, kb_id, required_role="viewer", is_admin=False, dept_id=None, is_dept_admin=False)`，
取到 `kb_row` 后最前面加 `if is_admin: return True`；在 `admin`/`company` 分支之后、显式授权检查之前，新增 dept 分支：

```python
            # dept 范围：本部门成员只读，本部门管理员可管，他部门走显式授权
            if kb_row.scope == "dept" and dept_id and kb_row.dept_id == dept_id:
                if is_dept_admin:
                    return True
                return _ROLE_RANK.get(required_role, 0) <= _ROLE_RANK["viewer"]
```

- [ ] **Step 4: 跑绿**

- [ ] **Step 5: 提交** — `feat(fastapi): check_permission 补部门库读写规则`

---

## Task 6: 身份贯穿 agent 流式链路 + 删 run/get_agent_response

**Files:** `app/agent/agent_tools.py`、`app/agent/agent.py`

- [ ] **Step 1: agent_tools** — `_build_rag_filter` 改签名收身份：

```python
from app.services.kb_service import kb_service
from app.utils.auth_utils import RequestIdentity

async def _build_rag_filter(identity: Optional[RequestIdentity]) -> Optional[dict]:
    if not identity or not identity.user_id:
        logger.warning("[rag_summary_tools] 未拿到身份/user_id，本次检索不做用户隔离过滤")
        return None
    return await kb_service.build_accessible_filter(
        identity.user_id, is_admin=identity.is_admin, dept_id=identity.dept_id
    )
```

`rag_summary_tools(query, identity=None)`：`filter_meta = await _build_rag_filter(identity)`；日志改打 `identity.user_id if identity else '<空>'`。（删除原 `decode_django_jwt` 引入的旧 `_build_rag_filter(user_id)` 逻辑。）

- [ ] **Step 2: agent.py** — `_execute_tool(self, name, arguments, identity=None)`，注入处改为
`if name == "rag_summary_tools": args["identity"] = identity`；
`stream(self, query, history=None, identity=None)`，工具执行处 `await self._execute_tool(tc["name"], tc["args"], identity)`；
`get_agent_stream_response(query, session_id, identity)`：用 `identity.user_id` 取历史/存储，调用 `agent_loop.stream(query, history, identity=identity)`。

- [ ] **Step 3: 删死代码** — 删除 `AgentLoop.run`（含 `@traceable`）与模块级 `get_agent_response`。确认无引用：
`grep -rn "get_agent_response\|\.run(" backend/app`（`chat_service` 的引用在 Task 7 一并清理）。

- [ ] **Step 4: 路由** — `chat.py` 的 `query_stream` 加 `identity: RequestIdentity = Depends(get_current_identity)`，调用 `get_agent_stream_response(request.query, session_id, identity)`；import 增加 `get_current_identity, RequestIdentity`。

- [ ] **Step 5: 验证** — `pytest tests/ -v` 全绿；导入自检
`backend/.venv/Scripts/python.exe -c "import app.agent.agent, app.agent.agent_tools, app.router.chat"`（须无 ImportError）。

- [ ] **Step 6: 提交** — `refactor(fastapi): 部门身份贯穿 agent 流式链路并删除非流式死代码`

---

## Task 7: KB 写权限校验接线 + /rag/query 过滤 + 删 handle_agent_query

**Files:** `app/router/chat_service.py`、`app/router/chat.py`

- [ ] **Step 1: handle_create_kb** — 改用 `can_create_kb`：

```python
    async def handle_create_kb(self, identity, name, scope, dept_id, description):
        allowed, eff_dept = can_create_kb(
            scope, identity.is_admin, identity.is_dept_admin,
            identity.dept_id, dept_id,
        )
        if not allowed:
            raise HTTPException(status_code=403, detail="无权创建该范围/部门的知识库")
        return await kb_service.create_kb(
            owner_id=identity.user_id, name=name, scope=scope,
            dept_id=eff_dept, description=description,
        )
```

- [ ] **Step 2: 读写 handler 透传身份** — `handle_list_kbs`/`handle_get_kb`/`handle_update_kb`/`handle_delete_kb`/`handle_add_kb_member`/`handle_remove_kb_member`/`handle_list_kb_members`/`handle_list_kb_documents`/`handle_kb_query`/`handle_add_vector_single`/`handle_add_vector_multiple` 改收 `identity`，把 `is_admin`/`dept_id`/`is_dept_admin` 透传给 `kb_service.list_accessible_kbs` 与 `check_permission`。`kb_service` 对应方法（`update_kb`/`delete_kb`/`add_member`/`remove_member`/`list_members`）签名补 `is_admin=False, dept_id=None, is_dept_admin=False` 并透传给内部 `check_permission`。

- [ ] **Step 3: /rag/query 过滤** —

```python
    async def handle_rag_query_with_citations(self, query, identity):
        filter_meta = await kb_service.build_accessible_filter(
            identity.user_id, is_admin=identity.is_admin, dept_id=identity.dept_id)
        return await rag_service.get_documents_and_summary(query, filter_meta=filter_meta)
```

- [ ] **Step 4: 删 handle_agent_query** — 删除 `ChatService.handle_agent_query` 及顶部 `from app.agent.agent import get_agent_response` 这一未用 import。确认无路由引用（路由用的是 `get_agent_stream_response`）。

- [ ] **Step 5: 路由接线** — `chat.py` 所有 KB 路由与 `/rag/query` 把 `user_id`/`is_admin` 依赖替换/补充为 `identity: RequestIdentity = Depends(get_current_identity)`，并传 `identity` 给对应 handler。`/kb/list` 响应里 `is_admin` 取 `identity.is_admin`。

- [ ] **Step 6: 验证** — `pytest tests/ -v` 全绿；`import app.router.chat` 无错。

- [ ] **Step 7: 提交** — `feat(fastapi): KB 读写权限按部门身份校验 + /rag/query 用户过滤 + 删死代码`

---

## Task 8: 部门管理 FastAPI 代理端点

供前端账号管理转发 Django 部门 CRUD / set-dept / set-dept-admin。沿用 `/api/admin/users` 模式。

**Files:** `app/router/chat.py`

- [ ] **Step 1: 实现** — 在现有 `admin_set_admin` 之后新增（抽一个内部转发辅助，统一清代理 + `run_in_executor` + 转发 body）：

```python
async def _proxy_django(method: str, path: str, token: str, json_body=None):
    loop = asyncio.get_event_loop()
    resp = await loop.run_in_executor(
        None,
        lambda: requests.request(
            method, f"{DJANGO_API_URL}{path}",
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"},
            json=json_body,
            proxies={"http": None, "https": None},
            timeout=15,
        ),
    )
    return resp.json()
```

新增端点（均 `is_admin` 网关，非管理员 403）：
- `GET  /admin/departments`            → Django `GET  /user/departments/`
- `POST /admin/departments`            → Django `POST /user/departments/`（body: `{name}`）
- `PATCH  /admin/departments/{dept_id}`→ Django `PATCH  /user/departments/{dept_id}/`（body: `{name}`）
- `DELETE /admin/departments/{dept_id}`→ Django `DELETE /user/departments/{dept_id}/`
- `PATCH /admin/users/{user_uuid}/set-dept`       → Django `PATCH /user/{uuid}/set-dept/`（body: `{dept_id}`）
- `PATCH /admin/users/{user_uuid}/set-dept-admin` → Django `PATCH /user/{uuid}/set-dept-admin/`（body: `{is_dept_admin}`）

POST/PATCH 用 `request: dict = Body(...)`（或具体 pydantic 模型）接收并透传 body。

- [ ] **Step 2: 验证** — `import app.router.chat` 无错；启动 FastAPI 后 `GET /api/admin/departments`（带管理员 token）返回 Django 部门列表，非管理员返回 403。冒烟用 `curl`/浏览器在前后端联调时验。

- [ ] **Step 3: 提交** — `feat(fastapi): 新增部门管理代理端点（部门 CRUD / 分配部门 / 任命部门管理员）`

---

## Phase 2 验收标准

- `pytest backend/tests/ -v` 全绿（身份提取、`can_create_kb`、`assemble_rag_filter` 纯函数 + 装 aiosqlite 后 DB 集成测试）
- 本部门成员能检索/看到本部门 `dept` 库，他部门成员看不到（部门间隔离）
- 普通用户**不能**再建 `company` 库（修复漏洞）；部门管理员能建/管本部门 `dept` 库；`company`/`admin` 库仅总管理员
- `/api/rag/query` 按当前用户可见范围过滤（不再全库可检索）
- `AgentLoop.run`/`get_agent_response`/`ChatService.handle_agent_query` 已删除，无残留引用
- 部门管理代理端点可转发 Django，鉴权与 `/admin/users` 一致；FastAPI 调 Django 均清代理无 ReadTimeout
- 后端可正常 `import` 启动（无 ImportError），dev server 跑 worktree 代码

## 非目标（沿用设计文档）

- 不在 FastAPI 自建用户/部门表；不做多部门、部门层级；前端改动属 Phase 3。
