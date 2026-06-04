# Phase 5b：知识缺口前端页 设计

> 状态：brainstorming 已通过，待写实现计划
> 日期：2026-06-03
> 适用：LangChain-RAG-FastAPI-Service / front（Vue3 + Vant），对接 5a 的缺口 API

## 1. 目标与范围

为 Phase 5a 的知识缺口后端提供前端管理界面：一个列表页，展示缺口、按状态筛选、修改状态。**仅前端（5b）**，后端 API 已在 5a 完成（`GET /api/knowledge-gaps?status=`、`PATCH /api/knowledge-gaps/{id}`，按身份过滤、含越权防护）。

**前置事实（已探明）：** 前端栈 Vue3 + Vant 4 + Pinia + vue-router + axios。路由在 `front/src/router/index.js`（routes 数组 + lazy import + `meta:{title,keepAlive,requiresAuth}` + 全局守卫查 `jwt_token`）。API 调用模式：`import axios from 'axios'` + `axios.get('/api/...', { headers: authHeader() })`，`authHeader = () => ({ Authorization: 'Bearer ' + getToken() })`，token 取自 localStorage。管理页如 `AccountManagement.vue` 走 `/admin/*` 路由。视图在 `front/src/views/`，导航/入口在 `My.vue`（含管理员可见的 `AccountManagement` 入口，凭 `is_admin` 判断）。

## 2. 关键决策（brainstorming）

1. **入口/可见性**：两处入口、一个页面。后端 `list_gaps` 已按身份过滤（管理员看全部、普通用户看自己），所以**前端只做一个页面**，不需要权限分支；普通入口 + 管理员入口都导航到同一页面，内容由后端按身份返回。
2. **keepAlive**：`false`——每次进入拉最新缺口（避免 CLAUDE.md 记录的 keepAlive 状态残留坑）。

## 3. 页面与路由

- **新页面** `front/src/views/KnowledgeGaps.vue`，Vant 组件，风格参照 `KnowledgeBase.vue`。
- **路由**（`router/index.js` routes 数组追加一项）：
  ```js
  {
    path: '/knowledge-gaps',
    name: 'KnowledgeGaps',
    component: () => import('../views/KnowledgeGaps.vue'),
    meta: { title: '知识缺口', keepAlive: false, requiresAuth: true }
  }
  ```

## 4. 入口

在 `My.vue` 加两处入口（复用其现有 cell 列表与 `is_admin` 判断模式）：
- **普通入口**：所有登录用户可见的 cell「知识缺口」→ 跳 `/knowledge-gaps`。
- **管理员入口**：`is_admin` 为真时额外可见的 cell「知识缺口管理」→ 同样跳 `/knowledge-gaps`（管理员进入后端自动返回全部）。

（两入口指向同一路由；区分仅为导航语义，内容由后端决定。）

## 5. API 对接

新建一个轻量 API 封装（放 `KnowledgeGaps.vue` 内或 `front/src/utils/` 视实现简洁度），两个调用：
- 列表：`axios.get('/api/knowledge-gaps', { params: status ? { status } : {}, headers: authHeader() })` → `res.data.data.gaps` / `.total`。
- 改状态：`axios.patch('/api/knowledge-gaps/' + id, { status }, { headers: authHeader() })`。

`authHeader` 与 token 获取复用 `My.vue`/`AccountManagement.vue` 现有方式（localStorage 取 `jwt_token`）。

## 6. 列表交互与展示

- **列表项**（Vant `Cell`/`Card`）：`title`（标题）、`category`（Vant `Tag`）、`question`（原始问题）、`suggested_content`（建议补充，较长用 `van-collapse` 折叠）、`status`（状态 Tag，按状态着色：pending 灰/橙、reviewed 蓝、resolved 绿、ignored 默认）、`updated_at`（时间，可截断显示）。
- **状态筛选**：顶部 Vant `Tabs`——全部 / 待处理 / 已查看 / 已解决 / 已忽略；切换调 API 带（或不带）`status` 参数重新拉取。
- **状态修改**：每条一个操作触发 Vant `ActionSheet`，列出可改状态（reviewed/resolved/ignored，可含「重置为待处理」）；选中 → `PATCH` → 成功 `Toast` + 刷新当前列表。
- **空/加载/错误**：无数据 `van-empty`；加载 `van-loading` 或 `van-pull-refresh` 下拉刷新；API 失败（含 403 越权）`Toast` 提示。

## 7. 错误处理

- 未登录：全局守卫已拦截（requiresAuth + jwt_token），跳登录。
- PATCH 403（非管理员改他人）：捕获并 `Toast`「无权修改」。
- API 网络/500：`Toast`「加载失败，请重试」。

## 8. 测试 / 验证

前端以**真实起服务 + 浏览器走查**为主（现有前端仅零星 `.mjs` 单测，不强制为本页加单测）。执行阶段验证清单：
1. 管理员登录 → 看到全部缺口；普通用户登录 → 只看到自己的。
2. 状态 Tabs 筛选正确。
3. ActionSheet 改状态 → 成功提示 + 列表刷新 + 后端状态持久化。
4. 空态（无缺口）展示正常。
5. 两处入口（普通 / 管理员）都能进入。

启动方式：后端 `AGENT_ENGINE=graph` 起在 8000（已含 5a 缺口 API，首次启动 `init_db` 自动建 `knowledge_gaps` 表）；前端 `npm run dev` 起在 3000；用真实账号走查。

## 9. 非目标（5b 不做）

- 缺口的批量操作、导出。
- 缺口编辑（只改状态，不改内容）。
- 缺口 → 自动补充知识库（第二版）。
- 为本页新增前端单测框架（沿用现有走查方式）。
