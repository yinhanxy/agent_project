# 多智能体协同框架设计（LangGraph + 复用现有内核）

> 状态：已通过 brainstorming 评审，待落地
> 日期：2026-06-03
> 适用项目：LangChain-RAG-FastAPI-Service（backend/）

## 1. 背景与目标

现有系统已是一个成熟的**单 Agent + 工具调用**的 RAG 服务：`AgentLoop`
（`backend/app/agent/agent.py`）用一个 `for round_idx in range(max_rounds)` 循环驱动
OpenAI SDK 的 function-calling，配套真 token 流、SSE 事件协议、部门级权限过滤、
父子分块检索、重排序、token 估算/校准。

目标不是推倒重来，而是**为未来扩展性把编排框架立好**，使系统能支持：

1. 不断新增的 Task 能力（文档对比、报告生成、申请文本、知识缺口……以及更多）
2. Agent 之间多轮交互（一个 Agent 做完，另一个不满意可打回重做）
3. 多 Agent 并行分工（复杂任务拆子任务并行再汇总）
4. 动态多步规划（Agent 自主决定下一步调谁）

这四点恰好是「图编排」框架的能力域。结论：引入 **LangGraph** 作为编排引擎，
但**只替换编排层，不重写 LLM 调用层与 RAG/权限内核**。

### 已确认的不变量（不能破坏）

- 对外只有一个流式出口 `POST /api/agent/query/stream` →
  `StreamingResponse(get_agent_stream_response(...))`。
- SSE 协议固定为 `response`(token) / `usage` / `agent_plan` /
  `agent_step_update` / `agent_step` / `done`，**前端已深度对接，是硬契约**。
- `rag_service.get_documents_for_agent()` 已是 Knowledge Agent 的现成内核
  （检索 + 重排 + 置信度阈值拒答 + citations）。其 `max_score < _CONFIDENCE_THRESHOLD`
  低置信分支，是 knowledge_gap 的天然触发信号。
- `langchain_core` 已是现有依赖，引入 `langgraph` 不是全新生态。
- 部门级权限通过 `identity`（`RequestIdentity`）显式注入，**不得改为隐式传递**。

### 选型回顾（为什么是 B）

- **方案 A 自研 orchestrator**：要支持上述四点等于重造一个简陋 LangGraph，维护成本全在自己。
- **方案 B（本设计）**：LangGraph 编排 + 现有 AgentLoop/RAG/工具作为节点内核复用。
  隐患集中在「两套体系的接缝」（流式桥接），可隔离、可增量验证、随时能停在可用状态。
- **方案 C 完全重构**：把权限注入、真流式、token 校准等踩过坑的东西全部重做，
  大爆炸式重构、难回退，风险最高。已否决。

## 2. 总体编排形态

用 LangGraph `StateGraph` 替换手写的 `for round_idx` 循环，**只替换编排层**：

```
          ┌─────────────┐
入口 ───▶ │ Coordinator │ (规划/路由节点)
          └──────┬──────┘
                 │ 条件边 (按 plan 分发)
       ┌─────────┼───────────┬──────────────┐
       ▼         ▼           ▼              ▼
 ┌──────────┐ ┌──────┐ ┌────────────┐ ┌──────────────┐
 │Knowledge │ │ Task │ │KnowledgeGap│ │(并行时多实例)│
 │  Agent   │ │Agent │ │   (缺口)   │ └──────────────┘
 └────┬─────┘ └──┬───┘ └─────┬──────┘
      └──────────┴───────────┘
                 │ 回到 Coordinator (条件边: 够了吗? 要不要再来一轮?)
                 ▼
          ┌─────────────┐
          │  Finalize   │ (汇总 + 流式输出最终回答)
          └─────────────┘
```

Coordinator 既是入口路由，又是反馈循环的汇合点——
`Knowledge → Coordinator → Task → Coordinator → Finalize` 的回边即「多轮交互/打回重做」。

**一期只走一遍**（Coordinator → Knowledge → Task → Finalize），但图结构从第一天就支持
回边和并行；以后加复杂度只加节点和边，不动引擎。这就是「框架先立好」。

## 3. 节点划分与内核复用

每个节点是**薄壳**，内部调用已有成熟代码，绝不重写：

| 节点 | 职责 | 复用的现有内核 |
|---|---|---|
| **Coordinator** | 一次 LLM 结构化调用，产出 `plan`（task_type + 需要哪些 Agent + 顺序） | 复用现有 LLM 封装，新增 `coordinator_prompt` |
| **Knowledge Agent** | 检索知识依据，判断 `is_enough` | 直接调 `rag_service.get_documents_for_agent()`，带 `identity` 过滤；低置信分支即 `is_enough=false` |
| **Task Agent** | 执行 4 类任务，内部按 task_type 分派到 tool | 文档对比/报告/申请文本三个 tool 新建在 `tools/`；LLM 调用复用现有封装 |
| **KnowledgeGap** | `is_enough=false` 时生成缺口条目并落库 | 新增 `knowledge_gap_service`（照 `document_service` 单例 + AsyncSession 套路） |
| **Finalize** | 汇总 + 流式吐出最终回答 token | 此处产生用户可见 token 流，对接 SSE |

补充约束：

1. 现有 `agent_tools.py` 五个工具**不动**，降一层作为 Knowledge/Task 节点内部可用工具。
2. Coordinator 多花一次 LLM 调用是本方案固定成本。缓解：简单 `knowledge_qa` 在
   Coordinator 里直接判定「无需 Task」，一轮结束；仅复杂任务走全图。
3. 权限 `identity` 只在入口注入一次进 State，Knowledge 节点从 State 取，
   绝不放进会被序列化/跨边界丢失的地方（见 §4）。

### Task Agent 的四类能力（一期全做）

- **文档对比**：多文档/新旧版差异，输出表格。复用现有 RAG 检索取证。
- **报告生成**：基于知识生成结构化报告（背景/适用范围/核心流程/风险点/参考文档）。
- **申请/说明文本生成**：基于制度生成出差申请等可用文本。
- **知识缺口记录**：查不到不乱答，生成待补充条目并落库（由 KnowledgeGap 节点承接）。

## 4. 共享状态 AgentState

LangGraph 全图传一个 `TypedDict`，核心是**区分可序列化数据与权限对象**：

```python
class AgentState(TypedDict):
    # ── 输入 ──
    query: str
    history: list                    # [(user, assistant), ...]
    identity: RequestIdentity        # ⚠️ 权限对象，约束见下

    # ── Coordinator 产出 ──
    plan: dict                       # {task_type, need_retrieval, need_task, route, reason}

    # ── Knowledge 产出 ──
    documents: list[str]
    citations: list[dict]            # 复用现有 citations 结构
    is_enough: bool
    confidence: float

    # ── Task / Gap 产出 ──
    task_result: str                 # 对比表 / 报告 / 申请文本
    knowledge_gap: dict | None

    # ── 轨迹 ──
    trace: Annotated[list[dict], operator.add]   # 各节点 append，reducer 合并
    final_answer: str
```

### 两条硬约束（对应方案 B 的隐患）

1. **`identity` 进 State 但永不持久化**：一期**不启用 LangGraph checkpointer**
   （那是要求 State 可序列化的元凶）。会话历史仍走现有 `session_manager`，
   不靠 LangGraph checkpoint。`identity` 只在内存 State 中流转，既不丢值也不被序列化；
   Knowledge 节点从 `state["identity"]` 取来传给 `rag_service`，
   与现状显式注入的安全性等价。
2. **`trace` 用 `Annotated[..., operator.add]` reducer**：LangGraph 标准做法，
   并行节点各自 append 轨迹不互相覆盖，为「并行 Agent」铺路。

## 5. 流式桥接（最关键的硬骨头）

目标：**LangGraph 内部跑多节点，但对外 SSE 协议一个字节都不改**，前端无感知。

做法：LangGraph `astream` 用双模式 `stream_mode=["custom", "messages"]`：

```python
async for mode, chunk in graph.astream(state, stream_mode=["custom", "messages"]):
    if mode == "messages":
        # Finalize 节点 LLM 吐的 token → 转成现有 {"type":"response","content":...}
        ...
    elif mode == "custom":
        # 节点用 get_stream_writer() 主动发的进度事件
        # → 转成现有 agent_plan / agent_step_update / agent_step
        ...
```

桥接规则：

1. **进度事件**：每个节点开始/结束时用 `get_stream_writer()` 发一条
   `{"kind":"step", ...}`。对外函数 `get_agent_stream_response` **保持不变**，
   内部把 custom 事件翻译成现有 `agent_plan`/`agent_step_update`/`agent_step` 帧。
   前端零改动。
2. **最终回答 token**：只有 **Finalize 节点**的 LLM 输出走 `messages` 模式流出，
   翻译成现有 `{"type":"response"}`。中间 Knowledge/Task 节点的 LLM 调用**不流 token**
   （内部产物，只发「已完成检索」这类 step 事件）。用户看到的 token 流仍然只有最终回答。
3. **`done` 帧**：图跑完后从最终 State 取 `citations`/`trace`/`tokens` 组装现有 `done` 帧。
   citations 不再依赖 ContextVar（Knowledge 节点直接写进 State），
   **顺手根除 ContextVar 跨边界丢值的老坑**。

**风险兜底（强制第一步）**：先做 spike——只搭「入口 → Finalize」两节点最小图，
验证 `messages` 模式能把 token 正确翻译成现有 SSE 让前端正常打字。
**Spike 通过 = 方案 B 可行性落地**，再铺开其余节点。

## 6. 错误处理

沿用现有语义，不发明新机制：

- 节点内异常 → 写入 `state["trace"]` 标记该节点 failed，**不中断全图**；
  Coordinator 看到失败可降级（如 Task 失败则退回只输出 Knowledge 的检索结果）。
- `rag_service` 的 `retrieval_failed` / 低置信 两分支语义**原样保留**：
  前者 Finalize 如实告知「检索服务不可用」，后者触发 KnowledgeGap 节点。
- Finalize 永远兜底输出文字，保证 SSE 流必然正常收尾
  （对应现有「最后一轮禁用工具强制收尾」的不变量）。

## 7. 数据持久化

照现有 SQLAlchemy 模式加两张表，model 加进 `backend/app/models/chat_history.py`
（`create_all` 自动建表），service 照 `document_service` 单例 + `AsyncSessionLocal` 套路。

```python
class KnowledgeGap(Base):           # 知识缺口表
    __tablename__ = "knowledge_gaps"
    # id, title, question, category, suggested_content(Text)
    # status: pending/reviewed/resolved/ignored (default pending)
    # user_id, dept_id (索引，沿用部门隔离)
    # created_at, updated_at

class AgentTrace(Base):             # 协同轨迹表（可选增强，一期落库）
    __tablename__ = "agent_traces"
    # id, session_id(索引), agent_name, input(Text), output(Text)
    # status, created_at
```

决策点：

1. **agent_trace 落库是可选增强**：轨迹本就通过 SSE `agent_step` 实时给前端。
   落库价值在事后回溯/复盘。一期就落（成本极低，一条 insert），但前端展示仍用实时 SSE，
   不依赖查库。
2. **knowledge_gap 配套 API**：新增 `GET /api/knowledge-gaps`（列表，带状态筛选）+
   `PATCH /api/knowledge-gaps/{id}`（改状态），挂在现有 `chat_router`，
   沿用 `get_current_identity` 鉴权。前端加一个「知识缺口」列表页。

## 8. 渐进式落地步骤

每步都可独立验证、随时能停在可用状态：

1. **Spike**：两节点最小图（入口 → Finalize），验证 `messages` 流桥接回 SSE，
   前端正常打字。← 不通就回头，不浪费后续工作。
2. 加 Knowledge 节点，复用 `get_documents_for_agent`，跑通「检索 → Finalize」，
   等价于现在的 RAG 问答。
3. 加 Coordinator 路由节点 + `AgentState`。
4. 加 Task 节点 + 三个 tool（对比/报告/申请文本）。
5. 加 KnowledgeGap 节点 + 表 + API + 前端页。
6. agent_trace 落库。
7. 切换 `/api/agent/query/stream` 到新图；旧 `AgentLoop` 保留一个 env 开关可回退。

## 9. 测试策略

- **契约测试优先**：现有 `test_agent_sse_steps`、`test_kb_permissions`、
  `test_agent_rag_generation_mode` 必须继续通过——它们是「没破坏对外契约」的证据。
  新图先让这些绿，再加新测试。
- 新增：
  - Coordinator 路由判定测试（给定 query → 期望 task_type）。
  - KnowledgeGap 触发测试（低置信 → 生成缺口落库）。
  - 权限测试扩展（identity 经 State 流转后 Knowledge 节点仍正确过滤，**防越权回归**）。
- Spike 阶段就要有「前端能正常打字」的手动验证（用 start-project 起服务实测）。

## 10. 目录结构变化（预期）

```
backend/app/
├── agent/
│   ├── agent.py              # 旧 AgentLoop 保留（env 开关回退用）
│   ├── graph/                # 新增：LangGraph 编排
│   │   ├── state.py          #   AgentState 定义
│   │   ├── build.py          #   StateGraph 组装
│   │   ├── stream_bridge.py  #   astream → 现有 SSE 协议翻译
│   │   └── nodes/
│   │       ├── coordinator.py
│   │       ├── knowledge.py
│   │       ├── task.py
│   │       ├── knowledge_gap.py
│   │       └── finalize.py
│   ├── agent_tools.py        # 不动
│   └── agent_middleware.py   # 不动
├── tools/                    # 新增：Task 能力
│   ├── compare_tool.py
│   ├── report_tool.py
│   └── form_tool.py
├── services/
│   └── knowledge_gap_service.py   # 新增
├── models/chat_history.py    # 新增 KnowledgeGap / AgentTrace model
└── router/chat.py            # 新增 knowledge-gaps 路由
```

## 11. 非目标（一期不做）

- 不接真实审批流、企业微信/飞书/钉钉。
- 不启用 LangGraph checkpointer（会话历史继续走 session_manager）。
- 不做复杂多 Agent 讨论/辩论机制（图结构支持，但一期不实现）。
- 不重写现有 RAG/权限/token 校准/流式底层。
