# Phase 5b：知识缺口前端页 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增一个知识缺口列表页（Vue3 + Vant），调用 5a 的缺口 API，支持按状态筛选与修改状态；在 My.vue 加入口。

**Architecture:** 单页面 `KnowledgeGaps.vue`，后端 `list_gaps` 已按身份过滤（管理员看全部、普通用户看自己），所以前端无权限分支。页面结构、组件导入、布局壳参照现有 `AccountManagement.vue`（`workbench-layout` + `desktop-rail` + `van-nav-bar`）。脚本逻辑（axios + authHeader、状态筛选、ActionSheet 改状态）在本计划写全。

**Tech Stack:** Vue3 (script setup) + Vant 4 + vue-router + axios。

**前置事实（已探明）：** 路由 `front/src/router/index.js`（routes 数组 + lazy import + `meta`）；API `axios.get('/api/...', { headers: authHeader() })`，`authHeader = () => ({ Authorization: 'Bearer ' + localStorage.getItem('jwt_token') })`；`AccountManagement.vue` 用 `<workbench-layout>` + `<desktop-rail>` + `<van-nav-bar>` + `<van-cell-group inset>` + `<van-cell>` + `<van-loading>` + `<van-empty>` + `<van-tag>`，Vant 组件全局可用；`My.vue` 的 `modern-cell-group` 是功能入口区，用 `<van-cell ... is-link @click="...">`，管理员判断用 `userStore.isAdmin`；Vant 4 函数式 API `import { showToast } from 'vant'`。

**所有命令在 `front/` 目录运行（先 `npm install`）。** 前端无单测框架——验证用 `npm run build`（编译/import 正确）+ 浏览器走查。

**范围：** 仅前端（5b）。后端缺口 API 在 5a 已完成。

---

## 文件结构

新建：
- `front/src/views/KnowledgeGaps.vue` — 缺口列表页

修改：
- `front/src/router/index.js` — 注册 `/knowledge-gaps` 路由
- `front/src/views/My.vue` — 加缺口入口 cell

---

## Task 1: 注册路由

**Files:**
- Modify: `front/src/router/index.js`

- [ ] **Step 1: 在 routes 数组追加路由**

在 `front/src/router/index.js` 的 `routes` 数组里（`AccountManagement` 那项之后、数组结束 `]` 之前）追加：
```js
  {
    path: '/knowledge-gaps',
    name: 'KnowledgeGaps',
    component: () => import('../views/KnowledgeGaps.vue'),
    meta: {
      title: '知识缺口',
      keepAlive: false,
      requiresAuth: true
    }
  },
```

- [ ] **Step 2: 验证（此步先建占位组件以便编译通过，正式实现在 Task 2）**

先建最小占位 `front/src/views/KnowledgeGaps.vue`：
```vue
<template><div>知识缺口</div></template>
<script setup></script>
```
Run（在 `front/` 目录）：
```bash
npm install
npm run build
```
Expected: 构建成功（路由 lazy import 指向的占位组件存在，无解析错误）。

- [ ] **Step 3: 行尾核查 + Commit**

```bash
git diff --stat src/router/index.js
git diff --stat --ignore-all-space src/router/index.js
```
（router/index.js 是既有文件；若两者差距大用 PowerShell 转回 CRLF：读 UTF8、`\r\n`→`\n`→`\r\n`、UTF8 无 BOM 写回。）
```bash
git add src/router/index.js src/views/KnowledgeGaps.vue
git commit -m "feat(front): 注册知识缺口页路由（占位组件）"
```

---

## Task 2: KnowledgeGaps.vue 页面

替换 Task 1 的占位组件为完整页面。布局壳（template 最外层 `workbench-layout`/`desktop-rail`/`van-nav-bar` 与组件 import）**参照同目录 `AccountManagement.vue` 的写法**确保与现有桌面/移动布局一致；下面给出完整可用实现，若 `WorkbenchLayout`/`DesktopRail` 的 import 路径与 AccountManagement 不同，以 AccountManagement 的为准。

**Files:**
- Modify: `front/src/views/KnowledgeGaps.vue`

- [ ] **Step 1: 写完整组件**

把 `front/src/views/KnowledgeGaps.vue` 替换为：
```vue
<template>
  <workbench-layout page-class="gap-workbench" single-content>
    <template #rail>
      <desktop-rail />
    </template>

    <div class="gap-container">
      <van-nav-bar title="知识缺口" fixed />

      <van-tabs v-model:active="activeStatus" @change="loadGaps" sticky offset-top="46px">
        <van-tab title="全部" name="" />
        <van-tab title="待处理" name="pending" />
        <van-tab title="已查看" name="reviewed" />
        <van-tab title="已解决" name="resolved" />
        <van-tab title="已忽略" name="ignored" />
      </van-tabs>

      <div class="gap-content">
        <van-loading v-if="loading" size="24px" vertical style="padding:32px 0">加载中</van-loading>
        <van-empty v-else-if="gaps.length === 0" description="暂无知识缺口" image-size="80" />

        <van-cell-group v-else inset>
          <van-cell
            v-for="g in gaps"
            :key="g.id"
            :title="g.title"
            :label="g.question"
          >
            <template #value>
              <div class="gap-meta">
                <div class="gap-tags">
                  <van-tag :type="statusType(g.status)">{{ statusLabel(g.status) }}</van-tag>
                  <van-tag plain type="primary">{{ g.category }}</van-tag>
                </div>
                <van-button size="mini" plain type="primary" @click="openAction(g)">改状态</van-button>
              </div>
            </template>
          </van-cell>
        </van-cell-group>
      </div>

      <van-action-sheet
        v-model:show="showAction"
        :actions="actions"
        cancel-text="取消"
        close-on-click-action
        @select="onSelectStatus"
      />
    </div>
  </workbench-layout>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'
import { showToast } from 'vant'

const gaps = ref([])
const loading = ref(false)
const activeStatus = ref('')
const showAction = ref(false)
const current = ref(null)

const authHeader = () => ({ Authorization: `Bearer ${localStorage.getItem('jwt_token')}` })

const STATUS_LABEL = { pending: '待处理', reviewed: '已查看', resolved: '已解决', ignored: '已忽略' }
const STATUS_TYPE = { pending: 'warning', reviewed: 'primary', resolved: 'success', ignored: 'default' }
const statusLabel = (s) => STATUS_LABEL[s] || s
const statusType = (s) => STATUS_TYPE[s] || 'default'

const actions = [
  { name: '标记已查看', value: 'reviewed' },
  { name: '标记已解决', value: 'resolved' },
  { name: '标记已忽略', value: 'ignored' },
  { name: '重置为待处理', value: 'pending' },
]

async function loadGaps() {
  loading.value = true
  try {
    const params = activeStatus.value ? { status: activeStatus.value } : {}
    const res = await axios.get('/api/knowledge-gaps', { params, headers: authHeader() })
    gaps.value = res.data?.data?.gaps || []
  } catch (e) {
    showToast('加载失败，请重试')
  } finally {
    loading.value = false
  }
}

function openAction(g) {
  current.value = g
  showAction.value = true
}

async function onSelectStatus(action) {
  if (!current.value) return
  try {
    await axios.patch(
      `/api/knowledge-gaps/${current.value.id}`,
      { status: action.value },
      { headers: authHeader() }
    )
    showToast('状态已更新')
    await loadGaps()
  } catch (e) {
    const code = e?.response?.status
    showToast(code === 403 ? '无权修改' : '更新失败')
  } finally {
    current.value = null
  }
}

onMounted(loadGaps)
</script>

<style scoped>
.gap-container { min-height: 100%; }
.gap-content { padding: 12px 0 32px; }
.gap-meta { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; }
.gap-tags { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
</style>
```

- [ ] **Step 2: 对齐布局壳 import + 核对响应结构**

(a) 打开 `front/src/views/AccountManagement.vue`，确认它对 `WorkbenchLayout` 和 `DesktopRail` 的 import 方式（是否在 `<script setup>` 里 `import WorkbenchLayout from '../components/WorkbenchLayout.vue'` 与 `import DesktopRail from '../components/DesktopRail.vue'`）。把相同的两行 import 加到 `KnowledgeGaps.vue` 的 `<script setup>` 顶部（紧跟现有 import 之后）。若 AccountManagement 用的是 kebab-case 全局注册而无显式 import，则本页也无需 import。

(b) 核对后端 `success_response` 的响应包裹结构：看 `AccountManagement.vue` 里成功响应是怎么取数据的（例如 `res.data.data` 还是 `res.data`），或直接看 `backend/app/core/success_response.py`。本页 `loadGaps` 写的是 `res.data?.data?.gaps`（对应 `success_response(data={gaps,total})` → `{...,"data":{"gaps":[...]}}`）。若实际结构不同（如数据直接在 `res.data` 顶层），按实际结构把 `res.data?.data?.gaps` 调整为正确路径。这一步取不对会导致列表恒为空。

- [ ] **Step 3: 验证编译**

Run（在 `front/` 目录）：
```bash
npm run build
```
Expected: 构建成功，无未定义组件/import 报错。若报 `WorkbenchLayout`/`DesktopRail` 未定义，按 Step 2 补 import。

- [ ] **Step 4: 行尾核查 + Commit**

```bash
git diff --stat src/views/KnowledgeGaps.vue
git diff --stat --ignore-all-space src/views/KnowledgeGaps.vue
```
（新文件，通常 LF，无需特别处理。）
```bash
git add src/views/KnowledgeGaps.vue
git commit -m "feat(front): 知识缺口列表页（筛选 + 改状态）"
```

---

## Task 3: My.vue 入口

**Files:**
- Modify: `front/src/views/My.vue`

- [ ] **Step 1: 在 modern-cell-group 加入口 cell**

在 `front/src/views/My.vue` 的 `<van-cell-group inset class="modern-cell-group">` 内（「设置」cell 附近、`isLogin` 为真的区域）追加两个 cell：
```html
        <van-cell v-if="isLogin" title="知识缺口" label="查看待补充的知识条目" icon="warning-o" is-link @click="router.push('/knowledge-gaps')" />
        <van-cell v-if="isLogin && userStore.isAdmin" title="知识缺口管理" label="管理全部用户的知识缺口" icon="records" is-link @click="router.push('/knowledge-gaps')" />
```
（`isLogin`、`userStore`、`router` 在 My.vue 的 `<script setup>` 中均已定义——前置事实已确认 `userStore.isAdmin` 与 `router.push` 可用。两个 cell 都跳同一路由：普通入口所有登录用户可见，管理入口仅管理员可见，进入后内容由后端按身份返回。）

- [ ] **Step 2: 验证编译**

Run（在 `front/` 目录）：
```bash
npm run build
```
Expected: 构建成功。

- [ ] **Step 3: 行尾核查 + Commit**

```bash
git diff --stat src/views/My.vue
git diff --stat --ignore-all-space src/views/My.vue
```
（My.vue 既有文件；若两者差距大用 PowerShell 转回 CRLF。确认 git diff 只显示新增的两个 cell。）
```bash
git add src/views/My.vue
git commit -m "feat(front): My 页加知识缺口入口"
```

---

## Task 4: 真实走查验证（controller + 用户）

**Files:** 无（验证任务）

> 前端无自动化测试，本步靠真实起服务 + 浏览器走查。subagent 实现到 Task 3 即可；本步由控制者用浏览器工具走查，或交用户实测。

- [ ] **Step 1: 起后端（含 5a 缺口 API）**

后端 `backend/` 目录，设 `AGENT_ENGINE=graph` 起在 8000（首次启动 `init_db` 会自动建 `knowledge_gaps` 表）。先确保知识库里有可触发缺口的数据，或直接通过 5a 的 e2e/聊天产生几条缺口（user_id 对应测试账号）。

- [ ] **Step 2: 起前端**

`front/` 目录 `npm run dev` 起在 3000。

- [ ] **Step 3: 走查清单**

用真实账号在浏览器走查：
1. 登录后 My 页能看到「知识缺口」入口；管理员账号还能看到「知识缺口管理」入口。
2. 进入 `/knowledge-gaps`：管理员看到全部缺口，普通用户只看到自己的。
3. 顶部 Tabs 切换状态（全部/待处理/已查看/已解决/已忽略）→ 列表按状态筛选。
4. 点「改状态」→ ActionSheet 弹出 → 选一个状态 → Toast「状态已更新」→ 列表刷新、状态变更持久（刷新页面仍在）。
5. 无缺口时显示空态「暂无知识缺口」。
6. 普通用户尝试改不属于自己的缺口（若构造到）→ Toast「无权修改」。

- [ ] **Step 4: 记录结论**

记录 `Phase 5b 通过 / 问题`。通过即可合并到 master。

---

## 后续

- **Phase 6：** `agent_traces` 落库（后端）。
- **Phase 7：** 默认引擎切 graph。
- 缺口触发敏感度增强（5a 遗留的 RAG 调优）。
