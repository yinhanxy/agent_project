# 部门化知识库权限体系 — Phase 3（前端）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Vue 前端按「总管理员 / 部门管理员 / 普通成员」三种角色渲染账号管理与知识库页面，并接入 Phase 2 的部门代理端点（账号部门分配、部门管理员任命、部门 CRUD）。

**Architecture:** 角色从 `user_info` 的 `is_admin / is_dept_admin / dept_id` 在 `store/user.js` 派生为 getter；`AccountManagement.vue` 与 `KnowledgeBase.vue` 仅做「按角色渲染 + 调代理端点」，所有隔离/鉴权由后端（Phase 1 Django + Phase 2 FastAPI 代理）保证。前端经 Vite 代理 `/api → FastAPI(8000)`，绝不直连 Django(8001)。

**Tech Stack:** Vue 3 `<script setup>`、Pinia（含 persist）、Vant 4、axios、vue-router。前端**无单测框架**（`front/package.json` 无 vitest/jest）。

---

## 0. 前置状态与依赖（执行前必读）

- 本 worktree 分支已 fast-forward 至 `master`（`93617d8`），含 Phase 1（Django）全部代码。
- **Phase 2（FastAPI 代理端点 + 知识库隔离）在别处并行开发，本计划执行时可能尚未就绪。** 因此：
  - 前端按下面「接口契约」对接 `/api/admin/...` 代理端点。
  - Phase 2 未就绪时，这些端点会返回 404；属预期，最终合并时联调对齐。
  - **每个任务的自动验证只用 `npm run build`（构建通过=语法/引用正确）**，端到端冒烟在 Phase 2 就绪后用浏览器做。
- **TDD 说明**：前端无单测设施，按用户全局 CLAUDE.md「以浏览器/CLI 实际验证为准」的偏好，本计划以「构建通过 + 手动冒烟」替代单元 TDD。若需引入 vitest 另开任务，不在本计划范围。
- **keepAlive**：本计划**不新增路由页面**——部门管理是 `AccountManagement.vue` 内的一个区块。`AccountManagement` 路由已 `keepAlive: true` 且用 `onActivated` 刷新；新增的部门数据也在 `onActivated` 内加载，无需改 keepAlive。

## 1. 接口契约（Phase 2 代理端点；前端按此实现）

代理端点位于 FastAPI，前端统一走 `/api/admin/...`（经 Vite 代理）。约定代理**原样转发 Phase 1 Django 的 JSON**（已在 `DjangoUserService/apps/user/views.py` 实现并验证）。错误响应统一形如 `{ "detail": "..." }`。

| 方法 | 路径 | 请求体 | 成功响应 |
|------|------|--------|----------|
| GET | `/api/admin/users` | — | `{ users: [{ uuid, username, email, telephone, is_admin, dept_id, dept_name, is_dept_admin, status, date_joined, last_login }], total }` |
| PATCH | `/api/admin/users/{uuid}/set-admin` | `{}` | `{ uuid, is_admin }` |
| GET | `/api/admin/departments` | — | `{ departments: [{ dept_id, name }], total }` |
| POST | `/api/admin/departments` | `{ name }` | `{ dept_id, name }`（201） |
| PATCH | `/api/admin/departments/{dept_id}` | `{ name }` | `{ dept_id, name }` |
| DELETE | `/api/admin/departments/{dept_id}` | — | `{ detail }` |
| PATCH | `/api/admin/users/{uuid}/set-dept` | `{ dept_id\|null }` | `{ uuid, dept_id }` |
| PATCH | `/api/admin/users/{uuid}/set-dept-admin` | `{ is_dept_admin: bool }` | `{ uuid, is_dept_admin }` |

要点：
- `set-admin` / `set-dept` / `set-dept-admin` 都用 **PATCH**（与现有 `set-admin` 一致）。
- `set-dept` 响应**不含 dept_name**；前端在变更成功后调 `loadUsers()` 重新拉取，避免本地 dept_name 过期。
- `set-dept` 传 `dept_id=null` 表示移出部门（后端会同时清掉 `is_dept_admin`）。
- `user_info`（`/user/detail/`，经 Redis 缓存）已含 `dept_id / dept_name / is_dept_admin`（见 `views.get_user_info`）。**权限变更后对方需重新登录才生效**（缓存 + JWT），UI 文案需说明。

## 2. 角色模型（前端派生）

```
is_admin === true            → super_admin（总管理员）
!is_admin && is_dept_admin   → dept_admin（部门管理员）
其它                          → member（普通成员）
```

各角色在两页的能力：

| 能力 | super_admin | dept_admin | member |
|------|:---:|:---:|:---:|
| 看到「账号管理」入口 | ✅ | ❌ | ❌ |
| 账号部门分配 / 任命部门管理员 / 部门 CRUD | ✅ | ❌ | ❌ |
| 创建 `personal` 库 | ✅ | ✅ | ✅ |
| 创建 `dept` 库 | ✅（任意部门） | ✅（本部门） | ❌ |
| 创建 `company` / `admin` 库 | ✅ | ❌ | ❌ |
| 管理（改名/删）某库 | ✅ | 本部门 `dept` 库 | 仅自己的 `personal` 库 |

> 账号管理整页仅 super_admin 可达（导航入口已按 `isAdmin` 控制），但页内操作仍按 `isSuperAdmin` 二次 gate，避免直接输入 URL 绕过。

## 3. 文件结构

| 文件 | 职责 | 改动类型 |
|------|------|---------|
| `front/src/store/user.js` | 新增角色派生 getter（`isSuperAdmin / isDeptAdmin / role / deptId / deptName`） | 修改 |
| `front/src/views/AccountManagement.vue` | 每个账号展示部门 + 分配部门 + 任命/取消部门管理员 + 部门 CRUD 区 | 修改（主要） |
| `front/src/views/KnowledgeBase.vue` | 创建库按角色给 scope 选项；KB 卡片展示部门归属；改名/删按角色 gate | 修改 |

不新增组件、不新增路由、不扩 `apiConfig`（admin 类端点沿用组件内硬编码路径，与现有 `set-admin` 风格一致）。

---

## Task 1: store/user.js 角色派生 getter

**Files:**
- Modify: `front/src/store/user.js:29-34`（getters 块）

- [ ] **Step 1: 在 getters 中追加角色派生 getter**

把现有 getters 块（第 29-34 行）：

```js
  getters: {
    getUserInfo: (state) => state.userInfo,
    getToken: (state) => state.token,
    getLoginStatus: (state) => state.isLogin,
    getUserBio: (state) => state.userInfo?.bio || state.userBio
  },
```

改为：

```js
  getters: {
    getUserInfo: (state) => state.userInfo,
    getToken: (state) => state.token,
    getLoginStatus: (state) => state.isLogin,
    getUserBio: (state) => state.userInfo?.bio || state.userBio,

    // ── 部门权限角色派生 ──────────────────────────────────────────
    // 总管理员：state.isAdmin 与 userInfo.is_admin 任一为真（KB 列表会单独刷新 state.isAdmin）
    isSuperAdmin: (state) => Boolean(state.isAdmin || state.userInfo?.is_admin),
    // 部门管理员：非总管理员且 is_dept_admin
    isDeptAdmin: (state) =>
      !Boolean(state.isAdmin || state.userInfo?.is_admin) && Boolean(state.userInfo?.is_dept_admin),
    // 统一角色字符串
    role: (state) => {
      if (Boolean(state.isAdmin || state.userInfo?.is_admin)) return 'super_admin';
      if (state.userInfo?.is_dept_admin) return 'dept_admin';
      return 'member';
    },
    deptId: (state) => state.userInfo?.dept_id || null,
    deptName: (state) => state.userInfo?.dept_name || null
  },
```

- [ ] **Step 2: 构建验证**

Run: `cd front && npm run build`
Expected: 构建成功，无报错（getter 仅新增，不影响既有逻辑）。

- [ ] **Step 3: Commit**

```bash
git add front/src/store/user.js
git commit -m "feat(front): user store 派生部门权限角色 getter

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 2: AccountManagement — 加载部门 + 展示账号部门 + 分配部门

**Files:**
- Modify: `front/src/views/AccountManagement.vue`

### 2.1 script：部门数据与分配逻辑

- [ ] **Step 1: 引入 userStore 并新增部门状态**

在 `<script setup>` 顶部 import 区（约 144-150 行）追加 userStore 引入：

```js
import { useUserStore } from '../store/user'
```

在 `const roleFilter = ref('all')`（约 157 行）之后追加：

```js
const userStore = useUserStore()
const isSuperAdmin = computed(() => userStore.isSuperAdmin)

// ── 部门数据 ──────────────────────────────────────────────────
const departments = ref([])
const loadingDepts = ref(false)
const deptNameById = computed(() => {
  const map = {}
  departments.value.forEach(d => { map[d.dept_id] = d.name })
  return map
})

// 分配部门弹窗
const showAssignDept = ref(false)
const assignTarget = ref(null)   // 正在分配部门的用户
const assigningDept = ref(false)
```

- [ ] **Step 2: 新增 loadDepartments / 分配部门 action**

在 `loadUsers` 函数（约 192-202 行）之后追加：

```js
const loadDepartments = async () => {
  if (!isSuperAdmin.value) return
  loadingDepts.value = true
  try {
    const res = await axios.get('/api/admin/departments', { headers: authHeader() })
    departments.value = res.data?.departments || []
  } catch (e) {
    showToast('加载部门失败：' + (e.response?.data?.message || e.response?.data?.detail || '未知错误'))
  } finally {
    loadingDepts.value = false
  }
}

const openAssignDept = (u) => {
  assignTarget.value = u
  showAssignDept.value = true
}

// 部门分配 action-sheet 选项：各部门 + 「移出部门」
const assignDeptActions = computed(() => {
  const actions = departments.value.map(d => ({ name: d.name, dept_id: d.dept_id }))
  actions.push({ name: '移出部门', dept_id: null, color: '#ee0a24' })
  return actions
})

const onAssignDept = async (action) => {
  const u = assignTarget.value
  if (!u) return
  assigningDept.value = true
  try {
    await axios.patch(
      `/api/admin/users/${u.uuid}/set-dept`,
      { dept_id: action.dept_id },
      { headers: authHeader() }
    )
    showToast(action.dept_id ? `已分配到「${action.name}」` : '已移出部门')
    await loadUsers()   // 重新拉取，刷新 dept_name / is_dept_admin
  } catch (e) {
    showToast('操作失败：' + (e.response?.data?.message || e.response?.data?.detail || '未知错误'))
  } finally {
    assigningDept.value = false
    assignTarget.value = null
  }
}
```

- [ ] **Step 3: onActivated 同时加载部门**

把文件末尾的 `onActivated(loadUsers)`（约 232 行）改为：

```js
onActivated(() => {
  loadUsers()
  loadDepartments()
})
```

### 2.2 template：账号部门展示 + 分配入口

- [ ] **Step 4: 用户 cell 内展示部门并加分配入口**

把用户列表 cell（约 73-101 行）整体替换为：

```html
        <van-cell-group v-else inset>
          <van-cell
            v-for="u in filteredUsers"
            :key="u.uuid"
            :title="u.username"
            :label="u.email"
          >
            <template #icon>
              <van-icon
                name="manager"
                :color="u.is_admin ? '#1989fa' : '#ccc'"
                size="22"
                style="margin-right:10px;flex-shrink:0"
              />
            </template>
            <template #value>
              <div class="user-meta">
                <div class="user-tags">
                  <van-tag v-if="u.is_admin" type="primary">总管理员</van-tag>
                  <van-tag v-else-if="u.is_dept_admin" type="success">部门管理员</van-tag>
                  <van-tag v-else type="default">普通用户</van-tag>
                  <van-tag plain type="warning">{{ u.dept_name || '未分配部门' }}</van-tag>
                </div>
                <div class="user-actions">
                  <span class="user-role-label">总管理员</span>
                  <van-switch
                    :model-value="u.is_admin"
                    size="18px"
                    :disabled="toggling === u.uuid || u.uuid === selfUuid"
                    :loading="toggling === u.uuid"
                    @update:model-value="toggleAdmin(u)"
                  />
                  <van-button
                    size="mini"
                    plain
                    type="primary"
                    :disabled="u.is_admin"
                    @click="openAssignDept(u)"
                  >分配部门</van-button>
                  <van-button
                    size="mini"
                    plain
                    :type="u.is_dept_admin ? 'danger' : 'success'"
                    :disabled="!u.dept_id || u.is_admin || deptAdminToggling === u.uuid"
                    :loading="deptAdminToggling === u.uuid"
                    @click="toggleDeptAdmin(u)"
                  >{{ u.is_dept_admin ? '取消部管' : '任命部管' }}</van-button>
                </div>
              </div>
            </template>
          </van-cell>
        </van-cell-group>
```

> 说明：原来用 `#right-icon` 放 tag+switch；改用 `#value` 容纳更多控件（部门 tag、分配部门、任命部管）。`toggleDeptAdmin` 与 `deptAdminToggling` 在 Task 3 加入。总管理员不可被分配部门/任命部管（`:disabled="u.is_admin"`）。

- [ ] **Step 5: 加入分配部门 action-sheet（template 内，紧邻根 workbench-layout 关闭前，约第 117 行 `</div>` 之后、`<template #context>` 之前任意稳定位置）**

在 `<tab-bar />`（约 115 行）之后、其外层 `</div>`（116 行）之前，或在 context 模板前插入：

```html
    <!-- 分配部门 -->
    <van-action-sheet
      v-model:show="showAssignDept"
      :actions="assignDeptActions"
      cancel-text="取消"
      :description="assignTarget ? `为「${assignTarget.username}」选择部门` : ''"
      @select="onAssignDept"
    />
```

- [ ] **Step 6: 加样式**

在 `<style scoped>` 末尾追加：

```css
.user-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
}
.user-tags {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
}
.user-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.user-role-label {
  font-size: 12px;
  color: #969799;
}
```

- [ ] **Step 7: 构建验证**

Run: `cd front && npm run build`
Expected: 构建成功。（`toggleDeptAdmin`/`deptAdminToggling` 尚未定义 → 本步骤会报「未定义」错误，因此先在 Task 3 Step 1 补齐再构建；若按顺序逐任务执行，将 Task 2 Step 7 与 Task 3 合并验证。）

> **执行提示**：Task 2 的模板引用了 Task 3 才定义的 `toggleDeptAdmin`/`deptAdminToggling`，二者强耦合。**建议把 Task 2 与 Task 3 作为一次提交**：先做 Task 3 Step 1（定义状态与函数），再做 Task 2 模板，最后统一构建+提交。下面 Task 3 据此编排。

---

## Task 3: AccountManagement — 任命/取消部门管理员

**Files:**
- Modify: `front/src/views/AccountManagement.vue`

- [ ] **Step 1: 新增 deptAdminToggling 状态与 toggleDeptAdmin**

在 Task 2.1 Step 1 的 `const assigningDept = ref(false)` 之后追加：

```js
const deptAdminToggling = ref(null)
```

在 Task 2.2 的 `onAssignDept` 之后追加：

```js
const toggleDeptAdmin = async (u) => {
  if (!u.dept_id) { showToast('请先为该账号分配部门'); return }
  const next = !u.is_dept_admin
  const action = next ? '任命' : '取消'
  try {
    await showConfirmDialog({
      title: `${action}部门管理员`,
      message: `确认${action} ${u.username} 为「${u.dept_name}」的部门管理员？`,
    })
  } catch {
    return
  }
  deptAdminToggling.value = u.uuid
  try {
    const res = await axios.patch(
      `/api/admin/users/${u.uuid}/set-dept-admin`,
      { is_dept_admin: next },
      { headers: authHeader() }
    )
    u.is_dept_admin = res.data?.is_dept_admin ?? next
    showToast(`已${action}部门管理员`)
  } catch (e) {
    showToast('操作失败：' + (e.response?.data?.message || e.response?.data?.detail || '未知错误'))
  } finally {
    deptAdminToggling.value = null
  }
}
```

- [ ] **Step 2: 完成 Task 2 的模板改动（若尚未做）**

确保 Task 2 Step 4/5/6 的模板与样式已落地。

- [ ] **Step 3: 构建验证（Task 2 + Task 3 一并）**

Run: `cd front && npm run build`
Expected: 构建成功，无未定义引用。

- [ ] **Step 4: Commit（Task 2 + Task 3）**

```bash
git add front/src/views/AccountManagement.vue
git commit -m "feat(front): 账号管理展示部门并支持分配部门/任命部门管理员

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4: AccountManagement — 部门 CRUD 管理区

**Files:**
- Modify: `front/src/views/AccountManagement.vue`

- [ ] **Step 1: 新增部门 CRUD 状态与函数**

在 Task 3 的 `toggleDeptAdmin` 之后追加：

```js
// ── 部门 CRUD ────────────────────────────────────────────────
const newDeptName = ref('')
const creatingDept = ref(false)

const createDept = async () => {
  const name = newDeptName.value.trim()
  if (!name) { showToast('请输入部门名称'); return }
  creatingDept.value = true
  try {
    await axios.post('/api/admin/departments', { name }, { headers: authHeader() })
    showToast('部门已创建')
    newDeptName.value = ''
    await loadDepartments()
  } catch (e) {
    showToast('创建失败：' + (e.response?.data?.message || e.response?.data?.detail || '未知错误'))
  } finally {
    creatingDept.value = false
  }
}

const renameDept = (d) => {
  showConfirmDialog({
    title: '重命名部门',
    message: `将「${d.name}」重命名为：`,
    // Vant 的 confirmDialog 无输入框，用 prompt 兜底（桌面端浏览器原生输入）
  }).then(async () => {
    const name = window.prompt('请输入新的部门名称', d.name)
    if (name === null) return
    const trimmed = name.trim()
    if (!trimmed) { showToast('部门名称不能为空'); return }
    try {
      await axios.patch(`/api/admin/departments/${d.dept_id}`, { name: trimmed }, { headers: authHeader() })
      showToast('已重命名')
      await loadDepartments()
      await loadUsers()  // 成员的 dept_name 随之更新
    } catch (e) {
      showToast('重命名失败：' + (e.response?.data?.message || e.response?.data?.detail || '未知错误'))
    }
  }).catch(() => {})
}

const deleteDept = (d) => {
  showConfirmDialog({
    title: '删除部门',
    message: `确认删除「${d.name}」？该部门成员将被移出部门（其部门管理员身份一并解除）。`,
    confirmButtonColor: '#ee0a24',
  }).then(async () => {
    try {
      await axios.delete(`/api/admin/departments/${d.dept_id}`, { headers: authHeader() })
      showToast('部门已删除')
      await loadDepartments()
      await loadUsers()
    } catch (e) {
      showToast('删除失败：' + (e.response?.data?.message || e.response?.data?.detail || '未知错误'))
    }
  }).catch(() => {})
}
```

> 说明：Vant 的 `showConfirmDialog` 不带输入框；重命名用原生 `window.prompt` 兜底（项目目标为桌面工作台）。若后续要更精致，可换 `showDialog` + 自定义 message slot，但本计划保持最小实现。

- [ ] **Step 2: 在 template 加入部门管理区块**

在「用户列表」`list-section`（约 103 行 `</div>` 结束）之后、「说明」区块（约 105-112 行）之前插入部门管理 section：

```html
      <!-- 部门管理 -->
      <div class="list-section" v-if="isSuperAdmin">
        <div class="section-header">
          <span class="section-title">部门管理</span>
          <van-button size="small" plain icon="replay" :loading="loadingDepts" @click="loadDepartments" />
        </div>

        <van-cell-group inset>
          <van-field
            v-model="newDeptName"
            placeholder="输入新部门名称"
            :disabled="creatingDept"
          >
            <template #button>
              <van-button size="small" type="primary" :loading="creatingDept" @click="createDept">
                新建
              </van-button>
            </template>
          </van-field>
        </van-cell-group>

        <van-loading v-if="loadingDepts" size="24px" vertical style="padding:24px 0">加载中</van-loading>
        <van-empty v-else-if="departments.length === 0" description="暂无部门" image-size="80" />
        <van-cell-group v-else inset style="margin-top:12px">
          <van-cell
            v-for="d in departments"
            :key="d.dept_id"
            :title="d.name"
          >
            <template #right-icon>
              <div style="display:flex;align-items:center;gap:8px">
                <van-button size="mini" plain @click="renameDept(d)">改名</van-button>
                <van-button size="mini" plain type="danger" @click="deleteDept(d)">删除</van-button>
              </div>
            </template>
          </van-cell>
        </van-cell-group>
      </div>
```

- [ ] **Step 3: 构建验证**

Run: `cd front && npm run build`
Expected: 构建成功。

- [ ] **Step 4: Commit**

```bash
git add front/src/views/AccountManagement.vue
git commit -m "feat(front): 账号管理新增部门 CRUD 区（仅总管理员）

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5: KnowledgeBase — 创建库按角色给 scope 选项

**Files:**
- Modify: `front/src/views/KnowledgeBase.vue`

- [ ] **Step 1: script 增加角色派生**

把 `const isAdmin = computed(() => userStore.isAdmin)`（约 420 行）替换为：

```js
const isSuperAdmin = computed(() => userStore.isSuperAdmin)
const isDeptAdmin = computed(() => userStore.isDeptAdmin)
const myDeptId = computed(() => userStore.deptId)
const myDeptName = computed(() => userStore.deptName)
// 兼容旧引用：isAdmin 等价于 super_admin
const isAdmin = isSuperAdmin
// 是否可创建“部门库”：总管理员或部门管理员（部门管理员须已归属部门）
const canCreateDeptKb = computed(() => isSuperAdmin.value || (isDeptAdmin.value && !!myDeptId.value))
```

> 注意：`loadKbs` 里有 `userStore.isAdmin = res.data.data.is_admin`（约 582 行），保留不动——它仍维护 super_admin 标志，`isSuperAdmin` getter 会读取它。

- [ ] **Step 2: 创建库 scope 单选按角色显示**

把创建弹窗的 `van-radio-group`（约 243-248 行）替换为：

```html
            <van-radio-group v-model="newKb.scope" direction="horizontal" style="flex-wrap:wrap;gap:8px">
              <van-radio name="personal">个人（私有）</van-radio>
              <van-radio v-if="isSuperAdmin" name="company">公开</van-radio>
              <van-radio v-if="canCreateDeptKb" name="dept">部门</van-radio>
              <van-radio v-if="isSuperAdmin" name="admin">管理员专属</van-radio>
            </van-radio-group>
```

> 变更点：`company`（公开）从「所有人可见」收紧为**仅 super_admin**（对齐设计第 4 节与 Phase 2 后端修复）；`dept` 对 dept_admin 开放。

- [ ] **Step 3: 创建库说明文案按角色**

把共享标签页内 `section-note`（约 176-178 行）替换为：

```html
              <p class="section-note">{{ createKbNote }}</p>
```

并在 script 中（Step 1 之后）追加：

```js
const createKbNote = computed(() => {
  if (isSuperAdmin.value) return '总管理员：可创建个人 / 公开 / 部门 / 管理员专属知识库'
  if (canCreateDeptKb.value) return '部门管理员：可创建个人或本部门知识库'
  return '可创建个人（私有）知识库'
})
```

- [ ] **Step 4: 创建时为部门库带上 dept_id（部门管理员）**

把 `beforeCloseCreateKb` 里的创建请求（约 600 行）：

```js
    await axios.post('/api/kb', newKb.value, { headers: authHeader() })
```

替换为：

```js
    const payload = { ...newKb.value }
    // 部门管理员创建部门库时，归属到自己的部门；总管理员由后端按需处理
    if (payload.scope === 'dept' && isDeptAdmin.value && myDeptId.value) {
      payload.dept_id = myDeptId.value
    }
    await axios.post('/api/kb', payload, { headers: authHeader() })
```

> 最终归属与越权校验由 Phase 2 后端保证；前端只是把已知 dept_id 一并提交。

- [ ] **Step 5: 构建验证**

Run: `cd front && npm run build`
Expected: 构建成功。

- [ ] **Step 6: Commit**

```bash
git add front/src/views/KnowledgeBase.vue
git commit -m "feat(front): 知识库创建按角色提供 scope 选项（部门管理员可建本部门库）

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 6: KnowledgeBase — 库部门归属展示 + 改名/删按角色 gate

**Files:**
- Modify: `front/src/views/KnowledgeBase.vue`

- [ ] **Step 1: 新增 canManageKb 与部门名解析**

在 Task 5 的 `createKbNote` 之后追加：

```js
// 解析某 dept_id 的展示名：本部门用 user_info 的 dept_name，否则回退 id
const deptNameOf = (deptId) => {
  if (!deptId) return ''
  if (deptId === myDeptId.value && myDeptName.value) return myDeptName.value
  return deptId  // 跨部门时仅展示 id（前端不持有全量部门表）
}

// 是否可管理（改名/删）某库
const canManageKb = (kb) => {
  if (!kb) return false
  if (isSuperAdmin.value) return true
  if (kb.scope === 'personal') return kb.owner_id === currentUserUuid.value
  if (kb.scope === 'dept') return isDeptAdmin.value && !!myDeptId.value && kb.dept_id === myDeptId.value
  return false  // company / admin 仅 super_admin
}
```

- [ ] **Step 2: KB 列表卡片展示部门归属**

把 KB 列表 cell（约 193-210 行）替换为：

```html
                    <van-cell
                      v-for="kb in group.items"
                      :key="kb.kb_id"
                      :title="kb.name"
                      :label="kbLabel(kb)"
                      is-link
                      @click="openKb(kb)"
                    >
                      <template #right-icon>
                        <div style="display:flex;align-items:center;gap:6px">
                          <van-tag v-if="kb.scope === 'dept' && kb.dept_id" plain type="primary">
                            {{ deptNameOf(kb.dept_id) }}
                          </van-tag>
                          <van-icon
                            v-if="canManageKb(kb)"
                            name="ellipsis"
                            size="20"
                            color="#969799"
                            style="padding: 4px 0 4px 8px"
                            @click.stop="openKbMenu(kb, $event)"
                          />
                        </div>
                      </template>
                    </van-cell>
```

> 变更点：`dept` 库展示部门 tag；操作菜单（`ellipsis`）只在 `canManageKb` 为真时显示——成员对部门/公开库只读。

- [ ] **Step 3: 操作菜单选项按 canManageKb 收紧**

把 `kbActionOptions`（约 471-477 行）替换为：

```js
const kbActionOptions = computed(() => {
  const kb = actionKb.value
  if (!kb || !canManageKb(kb)) return []
  return [
    { name: '重命名', color: '#323233' },
    { name: '删除', color: '#ee0a24' },
  ]
})
```

> 原逻辑「重命名对所有人可见」不正确；现在改名/删都受 `canManageKb` 控制（与 Step 2 的菜单按钮可见性一致，双保险）。

- [ ] **Step 4: 详情弹窗的「上传/删文档」按 canManageKb gate（可选但建议）**

在 KB 详情弹窗「文档列表」section header（约 300-303 行）的上传按钮加可见性控制：把

```html
            <van-button size="small" icon="plus" type="primary" plain @click="triggerKbUpload">上传</van-button>
```

替换为：

```html
            <van-button v-if="canManageKb(currentKb)" size="small" icon="plus" type="primary" plain @click="triggerKbUpload">上传</van-button>
```

并把文档项的删除图标（约 316-319 行）：

```html
                <van-icon name="delete-o" color="#ee0a24" size="18" style="padding:4px"
                  @click.stop="confirmDeleteDoc(doc)" />
```

替换为：

```html
                <van-icon v-if="canManageKb(currentKb)" name="delete-o" color="#ee0a24" size="18" style="padding:4px"
                  @click.stop="confirmDeleteDoc(doc)" />
```

> 注意：个人「我的文档」标签页里的删除图标（约 150-154 行，针对 `documents`）保持不变——那是用户自己的个人库文档，本就可删。

- [ ] **Step 5: 构建验证**

Run: `cd front && npm run build`
Expected: 构建成功。

- [ ] **Step 6: Commit**

```bash
git add front/src/views/KnowledgeBase.vue
git commit -m "feat(front): 知识库按角色展示部门归属并控制管理操作可见性

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 7: 端到端冒烟验证（Phase 2 就绪后）

**前置：** Phase 2 代理端点已就绪、FastAPI(8000) 与 Django(8001) 均在运行、dev server 跑在**本 worktree**（按全局 CLAUDE.md 第二步核对 `CommandLine` 路径）。

- [ ] **Step 1: 启动/确认 dev server 指向 worktree**

按项目 `start-project` skill 启动；确认 Vite dev server 工作目录为本 worktree 的 `front/`。

- [ ] **Step 2: 总管理员视角**

1. 用总管理员账号登录 → 左侧出现「账号管理」。
2. 账号管理：新建一个部门 → 列表出现；改名 → 名称更新；给某账号分配该部门 → 该账号出现部门 tag；任命其为部门管理员 → tag 变「部门管理员」；取消 → 复原；删除部门 → 成员部门 tag 变「未分配部门」。
3. 知识库：创建对话框出现「个人/公开/部门/管理员专属」四项；各建一个成功；列表中 `dept` 库显示部门 tag；每个库都有操作菜单，可改名/删。

- [ ] **Step 3: 部门管理员视角**

1. 用被任命为部门管理员的账号登录 → 无「账号管理」入口（符合预期）。
2. 知识库：创建对话框只出现「个人 / 部门」两项（无公开/管理员专属）；建一个部门库成功，归属为本部门。
3. 本部门 `dept` 库有操作菜单可改名/删；他部门或公开库**无**操作菜单（只读）。

- [ ] **Step 4: 普通成员视角**

1. 普通成员登录 → 无「账号管理」入口。
2. 知识库：创建对话框只有「个人（私有）」一项；本部门 `dept` 库、公开库可见但只读（无操作菜单、详情内无上传/删文档按钮）；个人库可正常增删。

- [ ] **Step 5: 行尾自查（commit 前若未做，补做）**

对每个改过的文件执行（PowerShell）：

```powershell
git diff --stat -- front/src/views/AccountManagement.vue
git diff --stat --ignore-all-space -- front/src/views/AccountManagement.vue
```

两者差距大说明 Edit 工具把 CRLF 翻成了 LF；按全局 CLAUDE.md 第 7 条处理（统一为 LF 并在 commit message 注明，或转回 CRLF）。

- [ ] **Step 6: 合并到 master（测试通过后）**

```powershell
cd <repo>
git switch master
git status                       # clean
git merge --ff-only claude/<task>
git push <remote> master
```

---

## 自检（写计划后回看 spec）

- **spec 覆盖**：① 账号部门展示→Task 2；部门下拉分配→Task 2；任命/取消部门管理员→Task 3；部门 CRUD→Task 4；操作仅总管理员可见→各 Task 用 `isSuperAdmin` gate + 导航入口。② 角色从 user_info 派生（store/user.js）→Task 1。③ KnowledgeBase 角色化：部门管理员「创建本部门库」入口→Task 5；展示库部门归属→Task 6；按角色控制操作可见→Task 6。④ 知识库列表/创建走 `/api/kb/...`、隔离靠后端、前端只按角色渲染→Task 5/6 未改 `/api/kb` 调用语义。⑤ 经 Vite 代理 `/api`、不直连 Django→全部用 `/api/...`。⑥ 不新增 keepAlive 页面→部门管理是 AccountManagement 内区块，无新路由。
- **类型一致性**：`isSuperAdmin/isDeptAdmin/deptId/deptName` 在 Task 1 定义，Task 2-6 一致引用；`canManageKb/canCreateDeptKb/deptNameOf` 在 KnowledgeBase 内定义并使用；`toggleDeptAdmin/deptAdminToggling` 跨 Task 2/3 一致（已在执行提示中合并验证）。
- **占位符**：无 TODO/TBD；每个改动均给出可粘贴代码。
- **已知耦合**：Task 2 模板依赖 Task 3 的函数 → 已在 Task 3 合并构建+提交。
