# Phase 5a：知识缺口记录（后端）设计

> 状态：brainstorming 已通过，待写实现计划
> 日期：2026-06-03
> 适用：LangChain-RAG-FastAPI-Service / backend，承接 Phase 1-4 的 LangGraph 多 Agent 编排

## 1. 目标与范围

让系统在"查不到足够依据"时**不强行作答**，而是生成结构化的知识缺口记录落库，并如实告知用户当前无依据、已记录待补充条目。本设计是设计文档 §4.3.4 + §8.5 + §9.3/9.4 的落地，**仅后端（5a）**：KnowledgeGap 节点 + `knowledge_gaps` 表 + service + CRUD API + 图接入。前端缺口列表页是 5b，另开计划。

**前置（已在 master 59da269）：** LangGraph 图 `coordinator→(条件)→knowledge→(条件)→task|finalize`；`finalize` 支持 `state["task_messages"]` 流式；`coordinator` 产 `plan={task_type,need_retrieval,reason}`，`task_type` 含 `knowledge_gap`；`knowledge` 产 `is_enough`；`_stream.safe_get_stream_writer`；`nodes/task.py` 有 `route_after_knowledge`。模型集中在 `models/chat_history.py`，service 用 `AsyncSessionLocal` 单例模式（参考 `document_service`）。

## 2. 已确认决策（brainstorming）

1. **触发**：`is_enough == False`（主，检索后的事实信号）**或** `plan.task_type == "knowledge_gap"`（辅，coordinator 判定）。任一满足即记录缺口。
2. **去重**：精确问题文本去重——同 `user_id` + 相同 `question` + `status='pending'` 已存在则只更新 `updated_at`、不新增。无需 embedding。
3. **范围**：先做 5a 后端，5b 前端另开计划。
4. **缺口内容生成**：方案 B——KnowledgeGap 节点调一次 LLM 生成结构化 `{title, category, suggested_content}`（`suggested_content` 列出"建议补充什么"，才有管理价值）。

## 3. 图接入与路由

`route_after_knowledge`（在 `nodes/task.py`，本设计扩展它）按以下优先级返回，**缺口判断优先于 task**（无依据不该走 task 强行生成）：

```
knowledge 之后：
  is_enough == False  或  plan.task_type == "knowledge_gap"   → "knowledge_gap"
  task_type ∈ {document_compare, report_generation, document_generation} 且 documents 非空  → "task"
  否则                                                          → "finalize"
```

图结构：
```
coordinator →(条件)→ knowledge | finalize
knowledge →(条件 route_after_knowledge)→ knowledge_gap | task | finalize
knowledge_gap → finalize
task → finalize
finalize → END
```

## 4. KnowledgeGap 节点（`nodes/knowledge_gap.py`）

职责（按顺序）：
1. **生成结构化缺口**：调一次 `chat_model.ainvoke` 让其输出 JSON `{title, category, suggested_content}`；用健壮解析（提取首个 `{...}`、JSON 失败兜底），兜底值：`title=用户问题截断`、`category="unknown"`、`suggested_content="建议补充该问题相关的制度依据。"`。
2. **落库**：调 `knowledge_gap_service.save_gap(user_id, dept_id, title, question=state["query"], category, suggested_content)`，`identity` 从 `state.get("identity")` 取（无 identity 时 user_id 用空串、dept_id None）。落库 try/except 包裹，**失败不阻塞**（记 trace，继续告知用户）。
3. **构造 task_messages**：写入 `state["task_messages"]`，让 finalize 流式输出告知文本（"当前知识库未找到关于…的明确依据，已生成待补充知识条目：标题/建议补充内容…"）。复用 Phase 4 的 task_messages 机制，不新增流式出口。
4. **进度事件**：用 `safe_get_stream_writer` 发 `id="task_execute"` 的 step（running→done，title="记录知识缺口"）。

token：节点内 LLM 调用的 langgraph_node 为 `knowledge_gap`，被 bridge 的 `langgraph_node=="finalize"` 过滤，不泄漏给用户。

## 5. 数据表 `knowledge_gaps`

加到 `models/chat_history.py`（`create_all` 自动建表）：

```
id            Integer PK autoincrement
user_id       String(64) 索引，缺口产生者
dept_id       String(64) 索引，可空（部门归属，备用）
title         String(255)
question      Text         去重键之一
category      String(64)
suggested_content  Text
status        String(20) 默认 'pending'   # pending/reviewed/resolved/ignored
created_at    DateTime(tz) server_default now
updated_at    DateTime(tz) server_default now, onupdate now
```

## 6. `knowledge_gap_service`（单例 + AsyncSessionLocal）

照 `document_service` 模式，三个方法：

- `save_gap(user_id, dept_id, title, question, category, suggested_content) -> None`
  去重：查同 `user_id` + `question` + `status='pending'`；存在则 `updated_at=now()`（touch）不新增；否则插入新行。
- `list_gaps(user_id, is_admin, status=None) -> list[dict]`
  管理员返回全部；普通用户只返回自己产生的（`user_id` 匹配）。`status` 给定时过滤。按 `updated_at desc` 排序。
- `update_status(gap_id, user_id, is_admin, status) -> bool`
  改状态；非管理员只能改自己的（`user_id` 匹配，否则返回 False / 抛 PermissionError）。`status` 限 4 个合法值，非法拒绝。

## 7. API（挂 `chat_router`，沿用 `get_current_identity`）

- `GET /api/knowledge-gaps?status=pending`
  → `success_response(data={"gaps":[...], "total":N})`。按 identity（is_admin / user_id）过滤。
- `PATCH /api/knowledge-gaps/{gap_id}` body `{"status":"reviewed"}`
  → 改状态；越权或不存在返回 403/404；成功 `success_response`。

## 8. 错误处理

- 缺口落库失败：节点 try/except，记 `trace` 标 failed，仍构造 task_messages 告知用户（降级，不让用户请求失败）。
- LLM 生成缺口结构失败：兜底规则值（见 §4.1）。
- API 越权：`update_status` 非管理员改他人缺口 → 403；缺口不存在 → 404。

## 9. 测试策略

- `knowledge_gap_service`：用 conftest `sqlite_db` fixture 测——去重（同问题不新增）、list 过滤（管理员 vs 普通用户）、update_status 越权防护、非法 status 拒绝。
- `knowledge_gap` 节点：monkeypatch `chat_model` + `knowledge_gap_service`，验证落库被调用（参数正确）、task_messages 构造、解析兜底。
- `route_after_knowledge` 扩展：`is_enough=False → knowledge_gap`；`task_type=knowledge_gap → knowledge_gap`；缺口优先于 task。
- API：`sqlite_db` 测 GET 过滤 + PATCH 越权。
- 集成：图在 is_enough=False 时经过 knowledge_gap 节点；全量回归既有测试不退化。

## 10. 非目标（5a 不做）

- 前端缺口列表页（5b）。
- 缺口的语义相似去重（仅精确文本去重）。
- 缺口 → 自动补充知识库（设计文档说第二版）。
- 缺口的部门级可见性细分（dept_id 存着备用，5a 只按 user/admin 过滤）。
