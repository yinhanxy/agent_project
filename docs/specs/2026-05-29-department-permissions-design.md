# 部门化知识库权限体系 — 设计文档

- 日期：2026-05-29
- 状态：已评审通过，待编写实现计划
- 范围：同一 monorepo 内的三个服务——Django 账号服务（`DjangoUserService/`，端口 8001）、FastAPI 知识库服务（`backend/`，端口 8000）、Vue 前端（`front/`，端口 3000）。三者独立运行，但代码在同一 git 仓库，可在一个 worktree 内一并实现、一次合并。

## 1. 背景与目标

当前知识库权限只有二元角色 `is_admin`（管理员/普通用户），缺少组织维度。需要引入「部门」组织结构，实现：

1. 每个账号归属一个部门
2. 部门之间知识库**不共享**
3. 每个部门有「部门管理员」
4. 有跨部门全权的「总管理员」

同时修复一个已发现的执行缺陷：本服务此前拿不到用户的 `dept_id`，导致 `_build_rag_filter` 的部门过滤形同虚设（详见 `backend/app/agent/agent_tools.py`）。

## 2. 现状与系统边界

- **账号体系是独立运行的 Django 服务（端口 8001），代码在本 monorepo 的 `DjangoUserService/`（被同一 git 仓库追踪，非 submodule）**：JWT 由 Django 签发，本 FastAPI 服务仅解析（`auth_utils.decode_django_jwt`）；用户信息（含 `is_admin`）从 Django API 拉取后缓存到 Redis（`:1:user:{user_id}`）。账号管理接口（`/admin/users`、`set-admin`）全部代理到 Django。「服务独立」不等于「仓库独立」——三个服务同仓。
- **知识库体系在本 FastAPI 服务**，且已有部门雏形：
  - `KnowledgeBase(scope ∈ {personal,dept,company,admin}, dept_id, owner_id)`
  - `KBPermission(kb_id, principal_id, principal_type ∈ {user,dept}, role)`
  - `kb_service.list_accessible_kbs(user_id, is_admin, dept_id)` 已预留 `dept_id` 参数，但逻辑里未真正使用，且调用方从未传入。
- **关键缺口**：人与部门的关系不存在——`auth_utils` 从不提取 `dept_id`，所以部门过滤拿不到输入。

**结论**：组织结构（部门、归属、角色）属于账号属性，应在 Django 同源管理；本服务消费 `dept_id`/角色做知识库隔离。采用「方案 A：Django 统一管组织结构」。

## 3. 角色模型

单部门归属：每个账号一个 `dept_id`（可为空）。三种角色：

| 角色 | 来源 | 范围 |
|------|------|------|
| 总管理员 `super_admin` | 现有 `is_admin` 升级 | 跨所有部门、所有库全权；管账号部门归属；任命部门管理员 |
| 部门管理员 `dept_admin` | 总管理员任命 | 仅本部门：建/删本部门 `dept` 库、给本部门成员细分库授权 |
| 普通成员 `member` | 默认 | 访问：个人库 + 本部门库 + 全公司公开库；可建个人库 |

部门管理员**不能**：管理成员部门归属、任命部门管理员（二者仅总管理员可做）。

## 4. 权限矩阵

知识库按 `scope` 分四层（沿用现有字段），可见性如下：

| 库类型 | 总管理员 | 部门管理员 | 本部门成员 | 他部门成员 |
|--------|:---:|:---:|:---:|:---:|
| 个人私有 `personal` | 仅自己 | 仅自己 | 仅自己 | 仅自己 |
| 部门内 `dept` | ✅ 全部门 | ✅ 本部门可管 | ✅ 只读 | ❌ |
| 全公司 `company` | ✅ | ✅ | ✅ | ✅ |
| 管理员专属 `admin` | ✅ | ❌ | ❌ | ❌ |
| 细分授权 `KBPermission` | ✅ | 本部门可授 | 被授可见 | 被授可见 |

核心诉求「部门间不共享」体现在 `dept` 行：他部门成员一律 ❌。

写权限：

| 操作 | 谁可以 |
|------|--------|
| 建/删/改 `personal` 库 | 所有人（仅限自己的） |
| 建/删/改 `dept` 库 | 本部门 `dept_admin` + `super_admin` |
| 建/删/改 `company`/`admin` 库 | 仅 `super_admin` |
| 对某库授权 `KBPermission` | 库所属部门的 `dept_admin` + `super_admin` |
| 改账号部门归属 / 任命部门管理员 | 仅 `super_admin`（在 Django 侧） |

## 5. 数据模型

### Django 侧（`DjangoUserService/apps/user/`）
- 新增 `Department` 模型（`models.py`）：主键 `dept_id`（ShortUUID，与 `User.uuid` 风格一致）、`name`
- `User` 模型（`db_table='user_service'`）增加：`dept`（外键 → `Department`，`null=True`，单部门归属）、`is_dept_admin`（bool，默认 `False`）；`is_admin` 继续表示总管理员
- 生成并执行数据库迁移（`makemigrations` + `migrate`）
> 注：`serializers.py` 顶部注释早已提到 `DepartmentSerializer`，但从未实现——本次正式落地。

### FastAPI 侧
- **无需新建用户/部门表**。复用现有 `KnowledgeBase`、`KBPermission`。
- `KnowledgeBase.dept_id` 引用 Django 的部门 ID（弱引用，字符串）。

## 6. 接口契约（Django → FastAPI）

Django 的 `user_info`（`/user/detail/` 返回，FastAPI 经 Redis 缓存）新增字段：

```json
{
  "uuid": "<用户ID>",
  "is_admin": false,
  "dept_id": "<部门ID|null>",
  "dept_name": "<部门名|null>",
  "is_dept_admin": false
}
```

- `is_admin`：现有，`true`=总管理员，保留兼容
- `dept_id`：新增，用户所属部门
- `dept_name`：新增，展示用
- `is_dept_admin`：新增，是否本部门管理员

角色由这些字段派生：`is_admin → super_admin`；否则 `is_dept_admin → dept_admin`；否则 `member`。

落点：在 `UserSerializer.Meta.fields`（`apps/user/serializers.py`）追加 `dept_id`、`dept_name`（`source='dept.name'`）、`is_dept_admin`，detail（`/user/detail/`）与 list（`/user/list/`）接口复用该序列化器即可返回。

## 7. FastAPI 实现拆解

1. **`auth_utils`**：新增依赖，从 `user_info` 提取 `dept_id` + `is_dept_admin`，打包成轻量「请求身份」对象（`user_id` / `is_admin` / `dept_id` / `is_dept_admin`）。
2. **身份传递**：沿 `stream → _execute_tool → rag_summary_tools → _build_rag_filter` 显式传递该身份对象。这是上次 citations 修复中引入的 `user_id` 显式传递的自然扩展（从传 1 个值改为传 1 个身份对象），不再依赖 ContextVar。
3. **`list_accessible_kbs` 补关键逻辑**：当前只纳入「被显式授权的库 + `company` 库」，需补一条 `scope=='dept' AND dept_id==用户dept_id`，使本部门成员自动可见本部门库（真正实现「部门内共享」）。
4. **`_build_rag_filter`**：补全调用参数（`is_admin` + `dept_id`），生成正确过滤条件；拿不到 `user_id` 时告警并返回 None（保持现有降级，但记录）。
5. **KB 写权限校验**：扩展 `chat_service.handle_create_kb` 等——`dept_admin` 可建/删本部门 `dept` 库、授权本部门成员；`company`/`admin` 仅 `super_admin`。修掉现有「`if not is_admin and scope in ('dept','admin')`」遗漏 `company` 的漏洞（当前普通用户可建 `company` 库）。
6. **补全 `/rag/query`**：`handle_rag_query_with_citations` 加入与 agent 路径一致的用户过滤（当前 `filter_meta=None`，全库可检索，越权）。
7. **删死代码**：`AgentLoop.run` / `get_agent_response` / `ChatService.handle_agent_query`（无任何调用者，非流式问答的遗留）。

## 8. 前端实现

- **账号管理页**（`AccountManagement.vue`）：展示/分配账号部门、任命部门管理员（调 Django API；仅总管理员可见操作）。
- **知识库页**（`KnowledgeBase.vue`）：按角色显示「创建部门库」入口，展示库的部门归属。
- AIChat 侧栏「当前知识库」已接入真实 `/api/kb/list`（前序工作完成）。

## 9. 关键设计决策

- **本部门 `dept` 库部门成员自动可见**，无需逐个授权。`KBPermission` 仅用于「细分授权」（把某库额外开放给特定个人或其他部门）。
- **保留四层可见性**（个人/部门/公司/管理员专属）。`company` 作为「确需全员可见」的层级保留（如公司制度）。
- **身份用显式参数传递，不用 ContextVar**——延续上次修复确立的原则。

## 10. 实现阶段与依赖

- **阶段 1（Django）**：`Department` 表、`User.dept_id`/`is_dept_admin`、`user_info` 加字段、部门/成员管理 API + 界面。
- **阶段 2（FastAPI）**：身份提取与传递、`list_accessible_kbs` 纳入本部门库、`_build_rag_filter` 补全、KB 写权限校验、`/rag/query` 补过滤、删死代码。
- **阶段 3（前端）**：账号管理部门分配、知识库页角色化。

三个服务同在本 monorepo，可在同一 worktree 内一并实现、一次性 fast-forward 合并。阶段 2 逻辑上依赖阶段 1 的接口契约（字段名先定好），实现顺序建议：Django 模型/迁移/序列化器 → FastAPI 消费与隔离 → 前端。身份对象在缺字段时降级为「无部门 + 普通成员」，保证灰度上线与回滚安全。

## 11. 非目标（YAGNI）

- 不做多部门归属（明确单部门）。
- 不做部门层级/子部门树。
- 不在 FastAPI 自建用户表或部门表（保持 Django 单一真相源）。
- 不做部门管理员管理成员归属、任命管理员（仅总管理员）。
