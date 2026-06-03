# LangGraph Phase 4：Task 节点 + 三个任务 tool 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Knowledge 之后增加 Task 节点，按 Coordinator 判定的 `task_type` 把检索到的文档交给对应任务 tool（文档对比 / 报告生成 / 申请文本），生成结构化结果。

**Architecture:** 关键设计决策——**tool 是"任务特定 prompt 构造器"（纯函数），最终 LLM 生成仍统一在 finalize 流式出口**。即 tool 接收 `(query, documents)` 返回 LLM messages（含任务专属 system prompt 与格式要求），Task 节点按 `task_type` 选 tool 把 messages 写入 `state["task_messages"]`，finalize 若发现 `task_messages` 就用它流式生成、否则用默认问答 prompt。这样保持"唯一流式 token 源 = finalize"的现有架构不被破坏，且 tool 可作纯函数独立单测。图由 `coordinator→knowledge→finalize` 扩展为在 knowledge 后增加一条按 task_type 的条件边到 task 节点。

**Tech Stack:** Python 3.12, LangGraph 1.1.6（`add_conditional_edges`）, langchain-core, 现有 `chat_model`, pytest + pytest-asyncio。

**前置（已在 master）：** Phase 1-3 完成——`app/agent/graph/` 下有 `state.py`（AgentState 含 plan）、`build.py`（START→coordinator→条件边→knowledge|finalize；knowledge→finalize）、`runner.py`、`stream_bridge.py`（按 `langgraph_node=="finalize"` 过滤 token）、`nodes/`（coordinator/knowledge/finalize）、`_stream.py`（`safe_get_stream_writer`）。`coordinator.py` 已产出 `plan={task_type, need_retrieval, reason}`，`task_type` 取值含 `document_compare/report_generation/document_generation/knowledge_qa/knowledge_gap/unknown`。

**所有命令在 `backend/` 目录下用 `uv run` 执行。** uv 命令的 `pyproject.toml:66 venv.path` warning 无害，忽略。新建文件无需行尾核查；修改既有文件（finalize.py / build.py / state.py）必须核查行尾（`git diff --stat` vs `--ignore-all-space`，差距大则用 PowerShell 转回 CRLF）。

**为什么没有 spike：** LangGraph 流式桥接、条件边、token 过滤均已在 Phase 1-3 用真实运行验证，Phase 4 不引入新机制，直接 TDD。

**范围：** 本计划是设计文档 §4.3 + §8 的 Phase 4。KnowledgeGap（Phase 5）、agent_trace 落库（Phase 6）、默认引擎切换（Phase 7）是后续独立计划。

---

## 文件结构

新建：
- `backend/app/tools/__init__.py` — 空包标识
- `backend/app/tools/compare_tool.py` — 文档对比的 prompt 构造（`build_messages`）
- `backend/app/tools/report_tool.py` — 报告生成的 prompt 构造
- `backend/app/tools/form_tool.py` — 申请/说明文本的 prompt 构造
- `backend/app/agent/graph/nodes/task.py` — Task 节点 + `task_type→tool` 映射 + `route_after_knowledge`
- `backend/tests/test_tools_prompt_builders.py` — 三个 tool 的单测
- `backend/tests/test_graph_task_node.py` — Task 节点单测
- `backend/tests/test_graph_task_routing.py` — knowledge 后路由 + 集成测试

修改：
- `backend/app/agent/graph/state.py` — 增加 `task_messages` 字段
- `backend/app/agent/graph/nodes/finalize.py` — finalize 优先使用 `task_messages`
- `backend/app/agent/graph/build.py` — 增加 task 节点与 knowledge 后条件边

---

## Task 1: 三个任务 tool（纯函数 prompt 构造器）

三个 tool 接口一致：`build_messages(query: str, documents: list[str]) -> list[dict]`，返回带任务专属 system prompt 和文档上下文的 LLM messages。

**Files:**
- Create: `backend/app/tools/__init__.py`（空）
- Create: `backend/app/tools/compare_tool.py`
- Create: `backend/app/tools/report_tool.py`
- Create: `backend/app/tools/form_tool.py`
- Test: `backend/tests/test_tools_prompt_builders.py`

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_tools_prompt_builders.py`:
```python
from app.tools import compare_tool, report_tool, form_tool


def _assert_common_shape(messages, query, doc):
    assert isinstance(messages, list) and len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    # 用户消息里必须带上文档内容与查询
    assert doc in messages[1]["content"]
    assert query in messages[1]["content"]


def test_compare_tool_builds_table_prompt():
    msgs = compare_tool.build_messages("新旧报销制度区别", ["旧版500", "新版600"])
    _assert_common_shape(msgs, "新旧报销制度区别", "旧版500")
    assert "表格" in msgs[0]["content"]          # system 要求输出表格


def test_report_tool_builds_report_prompt():
    msgs = report_tool.build_messages("售后处理流程报告", ["售后政策内容"])
    _assert_common_shape(msgs, "售后处理流程报告", "售后政策内容")
    assert "报告" in msgs[0]["content"]


def test_form_tool_builds_form_prompt():
    msgs = form_tool.build_messages("出差申请说明", ["差旅制度内容"])
    _assert_common_shape(msgs, "出差申请说明", "差旅制度内容")
    assert "申请" in msgs[0]["content"] or "说明" in msgs[0]["content"]


def test_tools_handle_empty_documents():
    # 无文档时仍返回合法 messages（finalize 会据 system 指示说明信息不足）
    for tool in (compare_tool, report_tool, form_tool):
        msgs = tool.build_messages("任意问题", [])
        assert len(msgs) == 2 and msgs[0]["role"] == "system"
```

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
uv run pytest tests/test_tools_prompt_builders.py -v
```
Expected: FAIL，`ModuleNotFoundError: No module named 'app.tools'`。

- [ ] **Step 3: 实现三个 tool**

Create `backend/app/tools/__init__.py`（空文件）。

Create `backend/app/tools/compare_tool.py`:
```python
"""文档对比任务：构造让 LLM 输出对比表格的 prompt。"""

_SYSTEM = (
    "你是企业知识库文档对比助手。基于提供的文档片段，对用户关心的对象"
    "（如新旧版制度）进行对比，输出 Markdown 表格。\n"
    "表格列建议：| 对比项 | 旧版/对象A | 新版/对象B | 影响 |。\n"
    "只基于给定文档，不得编造制度内容；若文档不足以对比，请明确说明知识库信息不足。"
)


def _format_context(documents: list[str]) -> str:
    if not documents:
        return "（未检索到相关文档）"
    return "\n\n".join(f"【文档片段{i}】\n{d}" for i, d in enumerate(documents, 1))


def build_messages(query: str, documents: list[str]) -> list[dict]:
    user = (
        f"请基于以下文档片段进行对比，并输出 Markdown 表格。\n\n"
        f"{_format_context(documents)}\n\n用户需求：{query}"
    )
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user},
    ]
```

Create `backend/app/tools/report_tool.py`:
```python
"""报告生成任务：构造让 LLM 输出结构化报告的 prompt。"""

_SYSTEM = (
    "你是企业知识库报告生成助手。基于提供的文档片段生成结构化 Markdown 报告，"
    "包含以下小节：## 背景、## 适用范围、## 核心流程、## 注意事项、## 风险点、## 参考文档。\n"
    "只基于给定文档，不得编造内容；若文档不足，请在相应小节注明信息缺失。"
)


def _format_context(documents: list[str]) -> str:
    if not documents:
        return "（未检索到相关文档）"
    return "\n\n".join(f"【文档片段{i}】\n{d}" for i, d in enumerate(documents, 1))


def build_messages(query: str, documents: list[str]) -> list[dict]:
    user = (
        f"请基于以下文档片段生成结构化报告。\n\n"
        f"{_format_context(documents)}\n\n报告主题：{query}"
    )
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user},
    ]
```

Create `backend/app/tools/form_tool.py`:
```python
"""申请/说明文本任务：构造让 LLM 生成规范申请文本的 prompt。"""

_SYSTEM = (
    "你是企业知识库申请/说明文本助手。基于公司制度文档，为用户生成规范的申请或说明文本，"
    "内容须符合制度要求、措辞正式。\n"
    "只基于给定文档中的制度依据，不得编造制度细节；若关键制度缺失，请提示用户补充。"
)


def _format_context(documents: list[str]) -> str:
    if not documents:
        return "（未检索到相关文档）"
    return "\n\n".join(f"【文档片段{i}】\n{d}" for i, d in enumerate(documents, 1))


def build_messages(query: str, documents: list[str]) -> list[dict]:
    user = (
        f"请基于以下制度文档片段，生成符合制度要求的申请/说明文本。\n\n"
        f"{_format_context(documents)}\n\n用户需求：{query}"
    )
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user},
    ]
```

- [ ] **Step 4: 运行测试确认通过**

Run:
```bash
uv run pytest tests/test_tools_prompt_builders.py -v
```
Expected: 4 个用例全 PASS。

- [ ] **Step 5: Commit**

```bash
git add app/tools/__init__.py app/tools/compare_tool.py app/tools/report_tool.py app/tools/form_tool.py tests/test_tools_prompt_builders.py
git commit -m "feat: 新增三个任务 tool（对比/报告/申请文本 prompt 构造器）"
```

---

## Task 2: AgentState 增加 task_messages 字段

**Files:**
- Modify: `backend/app/agent/graph/state.py`

- [ ] **Step 1: 在 AgentState 中加入 task_messages 字段**

在 `state.py` 的 `# 输出` 注释上方插入 Task 产出字段。修改后完整内容为：
```python
import operator
from typing import Annotated, Optional, TypedDict

from app.utils.auth_utils import RequestIdentity


class AgentState(TypedDict, total=False):
    """LangGraph 全图共享状态。

    约束（见设计文档 §4）：
    - identity 是权限对象，只在内存中流转，绝不持久化（一期不启用 checkpointer）。
    - trace 用 operator.add reducer，并行节点各自 append 不互相覆盖。
    """
    # 输入
    query: str
    history: list                       # [(user, assistant), ...]
    identity: Optional[RequestIdentity]

    # Coordinator 产出
    plan: dict                          # {task_type: str, need_retrieval: bool, reason: str}

    # Knowledge 产出
    documents: list                     # list[str]
    citations: list                     # list[dict]，复用现有 citations 结构
    is_enough: bool

    # Task 产出
    task_messages: list                 # finalize 用的任务专属 LLM messages；空则走默认问答

    # 输出
    final_answer: str

    # 轨迹（append-only）
    trace: Annotated[list, operator.add]
```

- [ ] **Step 2: 验证可导入**

Run:
```bash
uv run python -c "from app.agent.graph.state import AgentState; print('task_messages' in AgentState.__annotations__)"
```
Expected: 打印 `True`。

- [ ] **Step 3: 行尾核查**

Run:
```bash
git diff --stat app/agent/graph/state.py
git diff --stat --ignore-all-space app/agent/graph/state.py
```
两者差距大则用 PowerShell 转回 CRLF：
```powershell
$f = "app/agent/graph/state.py"
$text = [System.Text.Encoding]::UTF8.GetString([System.IO.File]::ReadAllBytes($f))
$text = ($text -replace "`r`n", "`n") -replace "`n", "`r`n"
$utf8 = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($f, $text, $utf8)
```

- [ ] **Step 4: Commit**

```bash
git add app/agent/graph/state.py
git commit -m "feat: AgentState 增加 task_messages 字段（Task 产出）"
```

---

## Task 3: Task 节点 + task_type→tool 映射 + knowledge 后路由

**Files:**
- Create: `backend/app/agent/graph/nodes/task.py`
- Test: `backend/tests/test_graph_task_node.py`

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_graph_task_node.py`:
```python
import pytest

from app.agent.graph.nodes.task import task_node


@pytest.mark.asyncio
async def test_task_node_uses_compare_tool():
    state = {
        "query": "新旧报销制度区别",
        "plan": {"task_type": "document_compare"},
        "documents": ["旧版500", "新版600"],
    }
    update = await task_node(state)
    msgs = update["task_messages"]
    assert msgs[0]["role"] == "system" and "表格" in msgs[0]["content"]
    assert "旧版500" in msgs[1]["content"]
    assert update["trace"][0]["agent"] == "task"


@pytest.mark.asyncio
async def test_task_node_uses_report_tool():
    state = {
        "query": "售后流程报告",
        "plan": {"task_type": "report_generation"},
        "documents": ["售后政策"],
    }
    update = await task_node(state)
    assert "报告" in update["task_messages"][0]["content"]


@pytest.mark.asyncio
async def test_task_node_unknown_type_yields_no_task_messages():
    # 防御：理论上路由不会把非任务类型导到 task，但若发生应安全降级（不设 task_messages）
    state = {"query": "x", "plan": {"task_type": "knowledge_qa"}, "documents": ["d"]}
    update = await task_node(state)
    assert "task_messages" not in update or not update.get("task_messages")
```

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
uv run pytest tests/test_graph_task_node.py -v
```
Expected: FAIL，`ModuleNotFoundError: app.agent.graph.nodes.task`。

- [ ] **Step 3: 实现 task 节点**

Create `backend/app/agent/graph/nodes/task.py`:
```python
from app.agent.graph._stream import safe_get_stream_writer
from app.agent.graph.state import AgentState
from app.tools import compare_tool, report_tool, form_tool

# task_type → 对应任务 tool（每个 tool 都有 build_messages(query, documents)）
_TOOL_MAP = {
    "document_compare": compare_tool,
    "report_generation": report_tool,
    "document_generation": form_tool,
}

# 需要走 Task 节点的任务类型（供 route_after_knowledge 使用）
TASK_TYPES_NEEDING_TASK = frozenset(_TOOL_MAP.keys())

_STEP_TITLE = {
    "document_compare": "生成文档对比",
    "report_generation": "生成报告",
    "document_generation": "生成申请文本",
}


async def task_node(state: AgentState) -> dict:
    """按 task_type 选 tool，构造任务专属 messages 写入 state；不调 LLM（生成留给 finalize）。"""
    task_type = (state.get("plan") or {}).get("task_type", "")
    tool = _TOOL_MAP.get(task_type)
    if tool is None:
        # 防御性降级：非任务类型不产生 task_messages，finalize 走默认问答
        return {"trace": [{"agent": "task", "status": "skipped",
                           "output": f"no tool for task_type={task_type}"}]}

    title = _STEP_TITLE.get(task_type, "执行任务")
    writer = safe_get_stream_writer()
    writer({"kind": "step", "id": "task_execute", "status": "running",
            "level": "info", "detail": f"正在{title}", "title": title})

    messages = tool.build_messages(state["query"], state.get("documents") or [])

    writer({"kind": "step", "id": "task_execute", "status": "done",
            "level": "success", "detail": f"已准备{title}", "title": title})

    return {
        "task_messages": messages,
        "trace": [{"agent": "task", "status": "done", "output": f"task_type={task_type}"}],
    }


def route_after_knowledge(state: AgentState) -> str:
    """knowledge 之后：任务类型且检索到文档则走 task，否则直接 finalize。"""
    plan = state.get("plan") or {}
    if plan.get("task_type") in TASK_TYPES_NEEDING_TASK and state.get("documents"):
        return "task"
    return "finalize"
```

- [ ] **Step 4: 运行测试确认通过**

Run:
```bash
uv run pytest tests/test_graph_task_node.py -v
```
Expected: 3 个用例全 PASS。

- [ ] **Step 5: Commit**

```bash
git add app/agent/graph/nodes/task.py tests/test_graph_task_node.py
git commit -m "feat: 新增 Task 节点（task_type→tool 映射）与 knowledge 后路由"
```

---

## Task 4: finalize 优先使用 task_messages

**Files:**
- Modify: `backend/app/agent/graph/nodes/finalize.py`
- Test: `backend/tests/test_graph_finalize_node.py`（追加用例）

- [ ] **Step 1: 写失败测试（追加到现有测试文件末尾）**

在 `backend/tests/test_graph_finalize_node.py` 末尾追加：
```python
@pytest.mark.asyncio
async def test_finalize_prefers_task_messages(monkeypatch):
    captured = {}

    async def _fake_ainvoke(messages):
        captured["messages"] = messages
        return _FakeMsg("对比表内容")

    import app.agent.graph.nodes.finalize as fz

    class _FakeChatModel:
        ainvoke = staticmethod(_fake_ainvoke)

    monkeypatch.setattr(fz, "chat_model", _FakeChatModel())

    task_msgs = [{"role": "system", "content": "对比助手"},
                 {"role": "user", "content": "对比文档"}]
    state = {"query": "随便", "documents": ["d"], "task_messages": task_msgs}
    update = await finalize_node(state)

    # finalize 应直接使用 task_messages，而非默认问答 prompt
    assert captured["messages"] == task_msgs
    assert update["final_answer"] == "对比表内容"
```

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
uv run pytest tests/test_graph_finalize_node.py::test_finalize_prefers_task_messages -v
```
Expected: FAIL（当前 finalize 忽略 task_messages，用 `_build_messages` 构造默认 prompt，`captured["messages"]` ≠ task_msgs）。

- [ ] **Step 3: 改 finalize_node 使用 task_messages**

修改 `backend/app/agent/graph/nodes/finalize.py` 的 `finalize_node`：把
```python
    messages = _build_messages(state)
```
改为
```python
    messages = state.get("task_messages") or _build_messages(state)
```
（其余不变：仍 `await chat_model.ainvoke(messages)`，仍发 running/done step。）

- [ ] **Step 4: 运行测试确认通过 + 既有 finalize 测试不退化**

Run:
```bash
uv run pytest tests/test_graph_finalize_node.py -v
```
Expected: 全部 PASS（原 2 个用例 + 新增 task_messages 用例）。

- [ ] **Step 5: 行尾核查 + Commit**

```bash
git diff --stat app/agent/graph/nodes/finalize.py
git diff --stat --ignore-all-space app/agent/graph/nodes/finalize.py
```
（finalize.py 是 Phase 2 新建文件，通常 LF；若差距大用 PowerShell 转回。）
```bash
git add app/agent/graph/nodes/finalize.py tests/test_graph_finalize_node.py
git commit -m "feat: finalize 优先使用 Task 节点产出的 task_messages"
```

---

## Task 5: build.py 接入 Task 节点与 knowledge 后条件边

图扩展为：`START→coordinator→(条件)→knowledge|finalize`；`knowledge→(条件)→task|finalize`；`task→finalize→END`。

**Files:**
- Modify: `backend/app/agent/graph/build.py`
- Test: `backend/tests/test_graph_task_routing.py`

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_graph_task_routing.py`:
```python
import pytest

from app.agent.graph.nodes.task import route_after_knowledge


def test_route_to_task_when_compare_with_docs():
    state = {"plan": {"task_type": "document_compare"}, "documents": ["d"]}
    assert route_after_knowledge(state) == "task"


def test_route_to_finalize_for_plain_qa():
    state = {"plan": {"task_type": "knowledge_qa"}, "documents": ["d"]}
    assert route_after_knowledge(state) == "finalize"


def test_route_to_finalize_when_task_type_but_no_docs():
    # 任务类型但没检索到文档：不强行执行任务，退回 finalize（由其说明信息不足）
    state = {"plan": {"task_type": "report_generation"}, "documents": []}
    assert route_after_knowledge(state) == "finalize"


@pytest.mark.asyncio
async def test_graph_routes_compare_through_task_node(monkeypatch):
    """document_compare + 有文档：图应经过 task 节点，finalize 收到 task_messages。"""
    import app.agent.graph.nodes.coordinator as co
    import app.agent.graph.nodes.knowledge as kn
    import app.agent.graph.nodes.finalize as fz

    class _Msg:
        def __init__(self, c):
            self.content = c

    async def _fake_coord(_m):
        return _Msg('{"task_type": "document_compare", "need_retrieval": true, "reason": "对比"}')

    async def _fake_get_docs(query, filter_meta=None):
        return {"documents": ["旧版500", "新版600"], "citations": [], "summary": "", "error": None}

    captured = {}

    async def _fake_final(messages):
        captured["messages"] = messages
        return _Msg("| 对比项 | 旧 | 新 |")

    class _Coord:
        ainvoke = staticmethod(_fake_coord)

    class _Final:
        ainvoke = staticmethod(_fake_final)

    monkeypatch.setattr(co, "chat_model", _Coord())
    monkeypatch.setattr(fz, "chat_model", _Final())
    monkeypatch.setattr(kn.rag_service, "get_documents_for_agent", _fake_get_docs)

    from app.agent.graph.build import build_graph
    graph = build_graph()
    result = await graph.ainvoke({"query": "新旧报销制度区别", "history": [], "trace": []})

    # finalize 收到的是 compare_tool 构造的任务 messages（system 含"表格"）
    assert "表格" in captured["messages"][0]["content"]
    assert result["final_answer"] == "| 对比项 | 旧 | 新 |"
```

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
uv run pytest tests/test_graph_task_routing.py -v
```
Expected: 路由单测可能已过（route_after_knowledge 在 Task 3 已实现），但集成测试 `test_graph_routes_compare_through_task_node` FAIL —— 当前 build.py 的图没有 task 节点，knowledge 直接到 finalize，finalize 收到默认 messages（system 是 main_prompt，不含"表格"）。

- [ ] **Step 3: 改 build.py**

修改 `backend/app/agent/graph/build.py` 为：
```python
from langgraph.graph import StateGraph, START, END

from app.agent.graph.state import AgentState
from app.agent.graph.nodes.coordinator import coordinator_node, route_after_coordinator
from app.agent.graph.nodes.knowledge import knowledge_node
from app.agent.graph.nodes.task import task_node, route_after_knowledge
from app.agent.graph.nodes.finalize import finalize_node


def build_graph():
    """Phase 4 图：
    START → coordinator →(条件)→ knowledge|finalize
    knowledge →(条件)→ task|finalize
    task → finalize → END
    """
    g = StateGraph(AgentState)
    g.add_node("coordinator", coordinator_node)
    g.add_node("knowledge", knowledge_node)
    g.add_node("task", task_node)
    g.add_node("finalize", finalize_node)

    g.add_edge(START, "coordinator")
    g.add_conditional_edges(
        "coordinator",
        route_after_coordinator,
        {"knowledge": "knowledge", "finalize": "finalize"},
    )
    g.add_conditional_edges(
        "knowledge",
        route_after_knowledge,
        {"task": "task", "finalize": "finalize"},
    )
    g.add_edge("task", "finalize")
    g.add_edge("finalize", END)
    return g.compile()
```

- [ ] **Step 4: 运行测试确认通过**

Run:
```bash
uv run pytest tests/test_graph_task_routing.py -v
```
Expected: 全部 PASS（3 个路由单测 + 1 个集成测试）。

- [ ] **Step 5: 行尾核查 + Commit**

```bash
git diff --stat app/agent/graph/build.py
git diff --stat --ignore-all-space app/agent/graph/build.py
```
（build.py 通常 LF；若差距大用 PowerShell 转回。）
```bash
git add app/agent/graph/build.py tests/test_graph_task_routing.py
git commit -m "feat: 图接入 Task 节点与 knowledge 后条件路由"
```

---

## Task 6: 全量回归 + 端到端验证

**Files:** 无（验证任务）

- [ ] **Step 1: 全量回归**

Run:
```bash
uv run pytest tests/ -q
```
Expected: 全部 PASS（既有契约测试 + Phase 1-3 全部 graph 测试 + 本 Phase 新增 tools/task/routing 测试）。任何失败原样贴报告，判断是否本次引入。

- [ ] **Step 2: 端到端真实验证（controller 执行，非 subagent）**

> 此步由控制者用临时脚本真实运行后删除，验证 document_compare 真实走 task 节点、finalize 用任务 prompt 流式生成、token 不泄漏（task 节点不产 token，coordinator/HyDE token 被过滤）。subagent 实现到 Step 1 即可。

临时脚本 `backend/_tmp_phase4_verify.py`（验证后删除）：
```python
import asyncio
from app.agent.graph.runner import graph_runner


async def run(q):
    events = []
    async for e in graph_runner.stream(q, history=[], identity=None):
        events.append(e)
    step_ids = [e["data"].get("id") for e in events if e["type"] == "agent_step_update"]
    tokens = "".join(e["data"] for e in events if e["type"] == "token")
    print(f"\nQ={q!r}")
    print(" step ids:", step_ids)
    print(" 出现任务执行步骤:", "task_execute" in step_ids)
    print(" 回答前120字:", tokens[:120])


async def main():
    await run("新版和旧版报销制度有什么区别")   # 期望 document_compare → 走 task


if __name__ == "__main__":
    asyncio.run(main())
```
运行：`PYTHONPATH=<backend绝对路径> uv run python _tmp_phase4_verify.py`
预期：出现 `task_understood` 与 `task_execute` 步骤；回答是对比性内容（若知识库有相关文档则为表格，无则说明信息不足）；token 干净（不含分类 JSON / HyDE 假设文档）。验证后删除临时脚本。

- [ ] **Step 3: 记录结论**

在本任务下方记录 `Phase 4 通过 / 问题`。通过即可合并到 master。

---

## 后续计划（不在本计划范围）

- **Phase 5：** KnowledgeGap 节点（`is_enough=False` 触发）+ `knowledge_gaps` 表 + API + 前端缺口页。coordinator 已能产出 `task_type=knowledge_gap`，可与 is_enough 信号结合。
- **Phase 6：** `agent_traces` 表落库（trace 已在 state 累积）。
- **Phase 7：** 默认引擎切 graph，旧 AgentLoop 留 env 开关回退。
