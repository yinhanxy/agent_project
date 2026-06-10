# Critic 证据级反馈回路 + history-aware query 改写 设计

> 状态：已通过 brainstorming 评审，待 spec 复核
> 日期：2026-06-10
> 适用项目：LangChain-RAG-FastAPI-Service（backend/）
> 前置：[2026-06-03-multi-agent-langgraph-design.md](./2026-06-03-multi-agent-langgraph-design.md)（多 agent 框架）、[2026-06-09-multi-agent-hardening.md](../plans/2026-06-09-multi-agent-hardening.md)（Phase 1/2 加固）

## 1. 背景与目标

现有 LangGraph 图（[backend/app/agent/graph/build.py](../../backend/app/agent/graph/build.py) 24-37 行）是**单向流水线**——`coordinator → knowledge → (knowledge_gap | task | finalize)`，不存在任何回边。这意味着：

- 检索质量差（query 写法问题、指代未消解）→ 错就错到底，没有挽救机会
- 现有路由 `is_enough=False` 直接进 `knowledge_gap`，**错失"改写 query 后能召回"的救援场景**
- 同时 [coordinator.py:66-71](../../backend/app/agent/graph/nodes/coordinator.py:66) 虽然能看到 history（已在 Phase 1 注入），但 **检索 query 仍是原始字符串**，"那它 2025 版改了什么"丢给 RAG 仍是同样字符串去查，召回大概率不准

加固计划 [2026-06-09-multi-agent-hardening.md](../plans/2026-06-09-multi-agent-hardening.md) 中 Phase 3 #1 标记 Critic 反馈回路为"开放设计，实现前必须先做需求/方案探索"。本设计是该探索的产出。

### 目标

- 在 `knowledge` 之后插入 **证据级 critic 节点**：对 `is_enough=False` 的检索结果做"是否能改写救援 / 是否真的超出范围"的判定
- 把 **history-aware query 改写**收进 critic 内部（同一次 LLM 调用顺手输出 `reformulated_query`），避免新增独立改写节点
- `max_revisions=1`：失败一次后强制走 `knowledge_gap`，控制成本与防死循环

### 显式不做（YAGNI）

- 答案级 critic（评估 finalize 草稿质量）：会破坏流式契约，需独立 spec
- DAG 规划器（Coordinator 单选 task_type → 多步任务）：Phase 3 #2，业务驱动后再做
- chunk metadata 过滤 / reranker 调优：另一条优化通道，与 critic 互补不互斥
- task_messages 路径补 history：已知限制 #1，独立优化项

## 2. 不变量（不能破坏）

1. **对外 SSE 协议零改动**：前端继续消费 `response`/`usage`/`agent_plan`/`agent_step_update`/`agent_step`/`done` 帧；critic 与重检索仅产生新的 `agent_step_update` 内容，不引入新帧类型
2. **finalize 一次成型流式输出**：critic 节点的 LLM token 由 [stream_bridge.py](../../backend/app/agent/graph/stream_bridge.py) 现行规则过滤（仅放行节点名为 `finalize` 的 token），不流给用户
3. **identity 仅在内存 state 流转**：不启用 LangGraph checkpointer，权限对象不持久化
4. **knowledge_gap 防幻觉机制保留**：[knowledge_gap.py:42-51](../../backend/app/agent/graph/nodes/knowledge_gap.py:42) 的"如实告知用户... 不要编造制度内容"prompt 不动
5. **现有测试基线**：`test_agent_sse_steps` / `test_graph_runner_sse` / `test_kb_permissions` / `test_graph_finalize_node` / `test_graph_coordinator_node` 必须继续通过

## 3. 总体形态（修正后的路由）

```
START → coordinator ──(need_retrieval=false)──→ finalize
              │
              └─(need_retrieval=true)→ knowledge ──┐
                                                   │
                                          ┌────────┴───────┐
                                  is_enough=true    is_enough=false
                                          │                 │
                                          ▼                 ▼
                                      task/finalize   critic_evidence
                                                            │
                                  ┌─────────────────────────┼──────────────────────┐
                                  │                         │                      │
                          verdict=relevant     verdict=needs_rewrite      verdict=out_of_scope
                                  │                         │                      │
                                  ▼                  revision_count<max?           ▼
                              task/finalize        ┌────────┴────────┐       knowledge_gap
                                                  yes               no
                                                   │                 │
                                                   ▼                 ▼
                                       knowledge（带 reformulated_query）  knowledge_gap
                                                   │
                                                   └──→ critic_evidence（再判一次）
```

### 路由要点（与原设计的差异）

- **删除"max_score 极低直接 gap"快速通道**：所有 `is_enough=False` 的 case 一律先经 critic（包括 0 命中、max_score 极低）。理由：低分恰恰是"指代未消解 / query 写法问题"的高发区，错失救援场景的代价大于多花一次 flash 调用
- **保留"高置信跳过 critic"快速通道**：`is_enough=True` 直接 task/finalize，不过 critic，省成本
- **critic 输出三档 verdict**：`relevant`（documents 其实够用，是阈值过严）/ `needs_rewrite`（query 写法问题，给改写）/ `out_of_scope`（知识库真没有）
- **revision_count 上限 1**：critic 第二次仍 fail 时强制走 knowledge_gap

## 4. 节点划分与内核复用

| 节点 | 状态 | 职责 |
|---|---|---|
| `critic_evidence` | **新增** | 输入：`query / history / documents / max_score`；输出：`{verdict, reason, reformulated_query?}`；模型：DeepSeek flash（与 coordinator/knowledge_gap 同档位）；prompt 走 [prompt_loader](../../backend/app/utils/prompt_loader.py) |
| `knowledge` | **小改** | 检测 `state.get("reformulated_query")`，有则用它替换 query 做检索；首次检索仍用原 query |
| `coordinator` / `finalize` / `task` / `knowledge_gap` | 不动 | — |

### 配置项（环境变量）

| 变量 | 默认 | 作用 |
|---|---|---|
| `AGENT_CRITIC_ENABLE` | `true` | critic 节点总开关；`false` 时退化到现行单向流水线（紧急回退用） |
| `AGENT_CRITIC_MAX_REVISIONS` | `1` | critic 触发重做的上限 |

### 阈值复用

不引入新阈值——`is_enough` 字段已由 [rag_service.py:251](../../backend/app/rag/rag_service.py:251) 用 `_GAP_THRESHOLD` 判定，本设计直接消费这个布尔值，避免阈值参数二次膨胀。

## 5. 状态扩展（AgentState）

在 [state.py](../../backend/app/agent/graph/state.py) 现有字段（`query / history / identity / plan / documents / citations / is_enough / task_result / knowledge_gap / trace / token_usage / final_answer / task_messages`）基础上追加：

```python
class AgentState(TypedDict, total=False):
    # ── 现有字段（略） ──

    # critic 反馈回路相关
    revision_count: Annotated[int, operator.add]   # critic 触发重做时 +1，reducer 累加
    critic_verdict: dict | None                    # 最近一次 critic 输出 {verdict, reason}
    reformulated_query: str | None                 # critic 给出的改写 query；knowledge 重检索时优先用
```

约束：
- `revision_count` 用 `operator.add` reducer，与 `trace`/`token_usage` 的并行处理一致
- `critic_verdict` 与 `reformulated_query` 不带 reducer，每次 critic 调用直接覆盖（最新一次为准）
- 新字段均不进 checkpoint（沿用 §2 不变量 3）

## 6. 流式契约影响（关键章节）

**结论：流式契约零改动，前端零修改即可消费**。

### 为什么不破裂

1. critic 节点 LLM 调用走 `chat_model.ainvoke()` 返回完整 message——**不经 messages 流**，不会被 LangGraph `astream` 的 `messages` 模式捕获
2. [stream_bridge.py](../../backend/app/agent/graph/stream_bridge.py) 现行规则就是"仅放行节点名为 `finalize` 的 token"；critic 节点无论叫什么都不会泄漏 token
3. 重检索时 `knowledge` 节点本来就不流 token（沿用现有规则）
4. 用户最终看到的 token 流仍然只有 finalize 一次成型的输出

### 进度事件

critic 与重检索通过 `safe_get_stream_writer()` emit 自定义 step 事件，runner 翻译成现有 `agent_step_update` 帧：

| 事件 id | title | detail | 触发时机 |
|---|---|---|---|
| `evidence_evaluating` | 评估检索证据 | "正在评估检索结果是否足以回答" | critic_evidence 节点开始 |
| `evidence_evaluated` | 已完成证据评估 | "证据评估：{verdict}" | critic_evidence 节点结束 |
| `knowledge_refetching` | 用更精细的查询重新检索 | "改写后的查询：{reformulated_query[:30]}..." | knowledge 节点重检索开始 |

前端 `agent_step_update` 帧消费方式不变，只是看到新的 id/title 文案——零代码修改。

### Spike 验证范围

本方案的 spike 不必验证流式契约破裂风险（那是 1b 答案级 critic 的硬骨头）。Spike 只验证：critic 节点能正确读 state、调 flash、返回结构化 verdict、token 计费正确进入 §5 `token_usage`。

## 7. query 改写与 critic 协同

不做独立的"history-aware 改写节点"——把它收进 critic 内部。

### 设计选择的理由

1. critic 已经要看 history（评估"那它呢"指代消解后的语义是否被检索到）
2. critic 已经要做 LLM 调用——多让它输出一个 `reformulated_query` 字段几乎零成本
3. 一个改写器 vs 两个节点（独立改写器 + critic）：图更简单，prompt 更聚焦

### 协同细节

- critic prompt 接收 `{query, history, documents, max_score}`，要求输出 JSON：
  ```json
  {
    "verdict": "relevant | needs_rewrite | out_of_scope",
    "reason": "<简短中文理由>",
    "reformulated_query": "<改写后的 query；verdict=needs_rewrite 时必填，否则 null>"
  }
  ```
- knowledge 节点重检索：`actual_query = state.get("reformulated_query") or state["query"]`
- coordinator 和 finalize **永远用原始 query** 维持上下文连贯，避免改写偏差污染最终答案
- critic 用结构化输出（与 [coordinator.py:38-44](../../backend/app/agent/graph/nodes/coordinator.py:38) 同套路：pydantic `BaseModel` + `with_structured_output(include_raw=True)`）

## 8. 错误处理

沿用 §2 不变量 5 的"节点异常不中断全图"语义（Phase 1 Task 2 已建立）：

| 失败场景 | 行为 | trace 状态 |
|---|---|---|
| critic LLM 异常 | 视为 verdict=relevant（不阻塞主路径），降级走 task/finalize | failed |
| critic 输出格式错（结构化解析失败） | 同上 | failed |
| 重检索异常 | 沿用 knowledge 节点已有兜底，降级为 empty docs → critic 再判 → 通常走 out_of_scope → gap | failed |
| revision_count 超过 max_revisions | 强制路由到 knowledge_gap，不再过 critic | — |
| LangGraph recursion_limit 兜底 | 默认 25，最坏路径 coordinator→knowledge→critic→knowledge→critic→knowledge_gap→finalize 仅 7 步，远低于上限 | — |

### 防幻觉补丁（顺带）

`verdict=relevant` 时低置信 documents 进 finalize——理论上仍可能被噪音误导。补一档 finalize prompt 升级：
- 当 `state["critic_verdict"]` 存在且 verdict=relevant 时，在 [finalize.py 的 `_build_messages`](../../backend/app/agent/graph/nodes/finalize.py:11) 注入额外的 user 指令："严格只引用文档原文片段，不做推断和综合；片段不直接覆盖的部分明确说明'文档未提及'"
- 0 成本，不动现有不变量

## 9. 持久化与可观测性

### AgentTrace 表（已存在，无需建表）

新增 trace 条目类型（写入 `agent_traces.agent_name` 字段）：

- `critic_evidence`：output 为 `{verdict, reason, reformulated_query}` 的 JSON
- `knowledge_retry`：output 为 `actual_query=<reformulated> max_score=<新分>`

### token_usage

critic / 重检索的 LLM 调用 token 通过 §5 现有 `Annotated[int, operator.add]` reducer 自动累加，不需 runner 改动。

### `done` 帧 trace 摘要

[runner.py](../../backend/app/agent/graph/runner.py) Phase 2 Task 5 已用 `final_trace` 替换写死的 `steps: []`，新增的 critic / knowledge_retry 条目自动出现，无需 runner 改动。

## 10. 渐进式落地（5 个 PR，每个独立可合）

每个 PR 都按 [全局 CLAUDE.md](file:///C:/Users/30207/.claude/CLAUDE.md) 的 worktree 工作流走（worktree 创建 → TDD → ff-merge → 清理）。

1. **Spike**：`critic_evidence` 节点写 + 强制 every-call 跑（不接路由）。验证 token 不泄漏、trace 落库正确、SSE 序列含 `evidence_evaluating`/`evidence_evaluated` 帧。Spike 不通过则停止，不进 PR 2
2. 接条件路由：`is_enough=True` 直接 task/finalize（不过 critic），`is_enough=False` 走 critic；critic 三档 verdict 路由到 task/finalize / 重检索 / gap
3. 接 `reformulated_query` + knowledge 重检索循环（max_revisions=1）
4. critic prompt 升级为 history-aware（在 prompt 模板中拼入 history）
5. finalize 防幻觉补丁（§8 末段的"严格引用"指令）

## 11. 测试策略

### 单元测试（节点级，monkeypatch 模型）

- `tests/test_graph_critic_node.py`：
  - critic 在 `verdict=relevant` 时返回 `{verdict, reason, reformulated_query=None}`
  - critic 在 `verdict=needs_rewrite` 时返回非空 `reformulated_query`
  - critic LLM 异常时降级 verdict=relevant + trace failed
  - critic 结构化解析失败时降级（同上）
  - critic prompt 包含 history（多轮指代场景）

### 路由测试

- `tests/test_graph_critic_routing.py`：
  - `is_enough=True` 不调 critic，直接走 task/finalize
  - `is_enough=False` + verdict=relevant → task/finalize
  - `is_enough=False` + verdict=needs_rewrite + revision=0 → knowledge 重检索
  - `is_enough=False` + verdict=needs_rewrite + revision=1 → knowledge_gap（max 上限触发）
  - `is_enough=False` + verdict=out_of_scope → knowledge_gap

### 集成测试（端到端 SSE）

- `tests/test_graph_critic_e2e.py`：
  - 低置信触发 → critic fail → 重检索 → critic pass → finalize 的端到端 SSE 帧序列：包含 `evidence_evaluating` / `knowledge_refetching` / `evidence_evaluated` / `response` token 流

### 回归基线

- 现有 `test_agent_sse_steps` / `test_graph_runner_sse` 在 critic 默认开启时仍绿（流式契约未破）
- `test_kb_permissions` 在 critic 启用时仍绿（权限 identity 经 critic 节点流转后 knowledge 节点仍正确过滤）
- `test_graph_finalize_node` / `test_graph_coordinator_node` 不退化

### 多轮回归

- `("差旅2023版上限", "500元")` 历史 + "那它2025版"新问 → critic 给出含"差旅与报销 2025 版"语义的 reformulated_query；重检索后回答能体现 2025 版差异

## 12. 目录结构变化

```
backend/
├── app/agent/graph/
│   ├── nodes/
│   │   ├── critic.py            # 新增
│   │   └── knowledge.py         # 改：支持 reformulated_query
│   ├── state.py                 # 改：3 个新字段
│   └── build.py                 # 改：插入 critic 节点 + 条件路由
├── app/utils/prompts/
│   └── critic_evidence.md       # 新增 critic prompt（如项目 prompt 走 prompt_loader）
├── app/config/agent.py          # 新增 AGENT_CRITIC_* 环境变量读取
└── tests/
    ├── test_graph_critic_node.py        # 新增
    ├── test_graph_critic_routing.py     # 新增
    └── test_graph_critic_e2e.py         # 新增
```

## 13. 非目标（一期不做）

1. 答案级 critic（评估 finalize 草稿质量、可能破坏流式契约）
2. Coordinator DAG 规划器（Phase 3 #2）
3. chunk metadata 过滤 / reranker 调优
4. 修改 stream_bridge / SSE 协议
5. `max_revisions` 用户级 / 会话级配置（先 env 全局，观察后再考虑放开）
6. task_messages 路径补 history（[加固计划已知限制 #1](../plans/2026-06-09-multi-agent-hardening.md)）
7. trace 查询 API + 前端 trace 详情页（[加固计划已知限制 #3](../plans/2026-06-09-multi-agent-hardening.md)，独立优化项）

## 14. 已知限制（备查）

1. **critic 仅看 documents 文本，不看 citations 元数据**：无法基于"文档版本/部门"等结构化字段做判断；如需要要等"chunk metadata 过滤"通道
2. **`reformulated_query` 由 LLM 生成，无人工兜底**：极端情况下改写比原 query 更差，靠 max_revisions=1 兜底（最多改写一次）
3. **AGENT_CRITIC_ENABLE 是全局开关**：无法按用户/会话粒度控制；按需要可在后续小迭代加 header 覆盖

## 15. 决策摘要（一句话回顾）

- **触发**：仅 `is_enough=False` 的 case 走 critic；高置信跳过
- **模型**：DeepSeek flash（与 coordinator 同档）
- **重做上限**：1
- **流式影响**：零改动
- **范围**：critic + history-aware query 改写一并交付（共用一次 LLM 调用）
- **路径修正**：删掉"低分直接 gap"快速通道，统一交给 critic 评估
