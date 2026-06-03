# LangGraph Phase 3：Coordinator 路由节点 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在图最前面加一个 Coordinator 节点，用一次 LLM 调用判定任务类型并决定是否需要知识检索，据此条件路由（需检索走 knowledge，否则直接 finalize），让系统具备"先理解任务再调度"的能力。

**Architecture:** Coordinator 节点对用户 query 做一次结构化分类，产出 `plan = {task_type, need_retrieval, reason}` 写入 AgentState。图结构由 `START→knowledge→finalize` 改为 `START→coordinator→(条件边)→knowledge|finalize→...→finalize→END`。Coordinator 的 LLM token 因节点名非 `finalize` 被现有 bridge 过滤，不泄漏给用户；它只发一条"任务识别"进度事件。

**Tech Stack:** Python 3.12, LangGraph 1.1.6（`add_conditional_edges`）, langchain-core, 现有 `chat_model`, pytest + pytest-asyncio。

**前置：** Phase 1-2 已完成并合并到 master：`app/agent/graph/` 下有 `state.py`（AgentState）、`build.py`（START→knowledge→finalize）、`runner.py`（GraphRunner）、`stream_bridge.py`（按 `langgraph_node=="finalize"` 过滤 token）、`nodes/finalize.py`、`nodes/knowledge.py`、`_stream.py`（`safe_get_stream_writer`）。

**所有命令在 `backend/` 目录下用 `uv run` 执行。** uv 命令的 `pyproject.toml:66 venv.path` warning 无害，忽略。

**关于范围：** 本计划是设计文档 §8 的 Phase 3。Task 节点（文档对比/报告/申请文本）是 Phase 4、KnowledgeGap 是 Phase 5，均为后续独立计划。本阶段 Coordinator 只决定 `need_retrieval`（走不走 knowledge）；`task_type` 字段记录下来供展示与 Phase 4 分流用，本阶段不据它分流到 Task 节点。

---

## 文件结构

新建：
- `backend/app/agent/graph/nodes/coordinator.py` — Coordinator 节点 + plan 解析 + 路由函数
- `backend/tests/test_graph_coordinator_node.py` — coordinator 节点与 plan 解析测试
- `backend/tests/test_graph_routing.py` — 条件路由函数测试

修改：
- `backend/app/agent/graph/state.py` — AgentState 增加 `plan` 字段
- `backend/app/agent/graph/build.py` — 接入 coordinator 节点 + 条件边
- `backend/app/agent/graph/runner.py` — `_initial_plan` 增加"识别任务类型"步骤、初始 state 加 `plan`

---

## Task 1: AgentState 增加 plan 字段

**Files:**
- Modify: `backend/app/agent/graph/state.py`

- [ ] **Step 1: 在 AgentState 中加入 plan 字段**

把 `state.py` 中 `query/history/identity` 这组输入字段下方、`# Knowledge 产出` 注释上方，插入 Coordinator 产出字段。修改后 `state.py` 完整内容为：
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

    # 输出
    final_answer: str

    # 轨迹（append-only）
    trace: Annotated[list, operator.add]
```

- [ ] **Step 2: 验证可导入**

Run（在 `backend/` 目录）:
```bash
uv run python -c "from app.agent.graph.state import AgentState; print('plan' in AgentState.__annotations__)"
```
Expected: 打印 `True`。

- [ ] **Step 3: 行尾核查（state.py 是已存在文件）**

Run:
```bash
git diff --stat app/agent/graph/state.py
git diff --stat --ignore-all-space app/agent/graph/state.py
```
两者差距大说明行尾被污染，用 PowerShell 转回原行尾：
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
git commit -m "feat: AgentState 增加 plan 字段（Coordinator 产出）"
```

---

## Task 2: Coordinator 节点 + plan 解析

Coordinator 调一次 `chat_model` 让其输出 JSON 分类结果，解析成 `plan`。解析必须健壮：LLM 可能用 ```json 代码块包裹或附带解释文字，需从中提取首个 JSON 对象；解析失败时兜底为"走检索"（保守，行为退化为 Phase 2，绝不因分类失败而漏检索）。

**Files:**
- Create: `backend/app/agent/graph/nodes/coordinator.py`
- Test: `backend/tests/test_graph_coordinator_node.py`

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_graph_coordinator_node.py`:
```python
import pytest

from app.agent.graph.nodes.coordinator import coordinator_node, _parse_plan


def test_parse_plan_plain_json():
    text = '{"task_type": "document_compare", "need_retrieval": true, "reason": "对比新旧制度"}'
    plan = _parse_plan(text)
    assert plan["task_type"] == "document_compare"
    assert plan["need_retrieval"] is True
    assert plan["reason"] == "对比新旧制度"


def test_parse_plan_with_code_fence_and_extra_text():
    text = '好的，分析如下：\n```json\n{"task_type": "knowledge_qa", "need_retrieval": true, "reason": "普通问答"}\n```\n以上。'
    plan = _parse_plan(text)
    assert plan["task_type"] == "knowledge_qa"
    assert plan["need_retrieval"] is True


def test_parse_plan_unknown_task_type_falls_back():
    text = '{"task_type": "啥也不是", "need_retrieval": false, "reason": "x"}'
    plan = _parse_plan(text)
    # 非法 task_type 归一为 unknown，但保留模型给的 need_retrieval
    assert plan["task_type"] == "unknown"
    assert plan["need_retrieval"] is False


def test_parse_plan_garbage_falls_back_to_retrieval():
    plan = _parse_plan("这不是 JSON")
    assert plan["task_type"] == "knowledge_qa"
    assert plan["need_retrieval"] is True  # 兜底：解析失败默认走检索


class _FakeMsg:
    def __init__(self, content):
        self.content = content


@pytest.mark.asyncio
async def test_coordinator_node_writes_plan(monkeypatch):
    async def _fake_ainvoke(_messages):
        return _FakeMsg('{"task_type": "report_generation", "need_retrieval": true, "reason": "要生成报告"}')

    import app.agent.graph.nodes.coordinator as co

    class _FakeChatModel:
        ainvoke = staticmethod(_fake_ainvoke)

    monkeypatch.setattr(co, "chat_model", _FakeChatModel())

    update = await coordinator_node({"query": "根据售后政策生成报告"})
    assert update["plan"]["task_type"] == "report_generation"
    assert update["plan"]["need_retrieval"] is True
    assert update["trace"][0]["agent"] == "coordinator"
```

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
uv run pytest tests/test_graph_coordinator_node.py -v
```
Expected: FAIL，`ModuleNotFoundError: app.agent.graph.nodes.coordinator`。

- [ ] **Step 3: 实现 coordinator 节点**

Create `backend/app/agent/graph/nodes/coordinator.py`:
```python
import json
import re

from app.agent.graph._stream import safe_get_stream_writer
from app.agent.graph.state import AgentState
from app.utils.factory import chat_model

# 合法任务类型（与设计文档一致）；非法值归一为 unknown
_TASK_TYPES = {
    "knowledge_qa", "document_compare", "document_generation",
    "report_generation", "knowledge_gap", "unknown",
}

_COORDINATOR_PROMPT = """你是企业知识库 Agent 的任务协调器。判断用户问题属于哪种任务类型，以及是否需要检索知识库。

只输出一个 JSON 对象，不要任何额外解释，格式：
{"task_type": "<类型>", "need_retrieval": <true|false>, "reason": "<简短中文理由>"}

task_type 取值：
- knowledge_qa：普通知识问答
- document_compare：多文档/新旧版对比
- document_generation：生成申请/说明等文本
- report_generation：生成结构化报告
- knowledge_gap：明显超出知识库范围、需记录缺口
- unknown：无法识别

need_retrieval：除非是与企业知识完全无关的闲聊，否则一律为 true。"""

# 兜底 plan：分类失败时保守走检索（行为退化为 Phase 2）
_FALLBACK_PLAN = {"task_type": "knowledge_qa", "need_retrieval": True,
                  "reason": "分类失败，默认走检索"}


def _parse_plan(text: str) -> dict:
    """从 LLM 输出中提取 JSON plan，健壮处理代码块/多余文字/非法值。"""
    if not text:
        return dict(_FALLBACK_PLAN)
    # 提取首个 {...} JSON 对象（兼容 ```json 包裹和前后解释文字）
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return dict(_FALLBACK_PLAN)
    try:
        data = json.loads(match.group(0))
    except (json.JSONDecodeError, ValueError):
        return dict(_FALLBACK_PLAN)

    task_type = data.get("task_type")
    if task_type not in _TASK_TYPES:
        task_type = "unknown"
    return {
        "task_type": task_type,
        "need_retrieval": bool(data.get("need_retrieval", True)),
        "reason": str(data.get("reason", "")),
    }


async def coordinator_node(state: AgentState) -> dict:
    """判定任务类型与是否需要检索。LLM token 因节点名非 finalize 被 bridge 过滤，不泄漏。"""
    writer = safe_get_stream_writer()
    writer({"kind": "step", "id": "task_understood", "status": "running",
            "level": "info", "detail": "正在识别任务类型", "title": "识别任务类型"})

    messages = [
        {"role": "system", "content": _COORDINATOR_PROMPT},
        {"role": "user", "content": state["query"]},
    ]
    msg = await chat_model.ainvoke(messages)
    text = msg.content if hasattr(msg, "content") else str(msg)
    plan = _parse_plan(text)

    writer({"kind": "step", "id": "task_understood", "status": "done",
            "level": "success", "detail": f"识别为：{plan['task_type']}",
            "title": "已识别任务类型"})

    return {
        "plan": plan,
        "trace": [{"agent": "coordinator", "status": "done",
                   "output": json.dumps(plan, ensure_ascii=False)}],
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run:
```bash
uv run pytest tests/test_graph_coordinator_node.py -v
```
Expected: 5 个用例全 PASS。

- [ ] **Step 5: Commit**

```bash
git add app/agent/graph/nodes/coordinator.py tests/test_graph_coordinator_node.py
git commit -m "feat: 新增 Coordinator 节点（任务分类 + 健壮 plan 解析）"
```

---

## Task 3: 条件路由函数

路由函数读 `state["plan"]["need_retrieval"]` 决定 coordinator 之后走 `knowledge` 还是直接 `finalize`。放在 coordinator.py 里（与产生 plan 的节点同文件，职责内聚）。

**Files:**
- Modify: `backend/app/agent/graph/nodes/coordinator.py`（追加路由函数）
- Test: `backend/tests/test_graph_routing.py`

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_graph_routing.py`:
```python
from app.agent.graph.nodes.coordinator import route_after_coordinator


def test_route_to_knowledge_when_need_retrieval():
    state = {"plan": {"task_type": "knowledge_qa", "need_retrieval": True}}
    assert route_after_coordinator(state) == "knowledge"


def test_route_to_finalize_when_no_retrieval():
    state = {"plan": {"task_type": "knowledge_qa", "need_retrieval": False}}
    assert route_after_coordinator(state) == "finalize"


def test_route_defaults_to_knowledge_when_plan_missing():
    # 没有 plan 时保守走检索（不漏检索）
    assert route_after_coordinator({}) == "knowledge"
```

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
uv run pytest tests/test_graph_routing.py -v
```
Expected: FAIL，`ImportError: cannot import name 'route_after_coordinator'`。

- [ ] **Step 3: 在 coordinator.py 末尾追加路由函数**

在 `backend/app/agent/graph/nodes/coordinator.py` 文件末尾追加：
```python


def route_after_coordinator(state: AgentState) -> str:
    """条件边：need_retrieval 为真走 knowledge，否则直接 finalize。缺 plan 时保守走 knowledge。"""
    plan = state.get("plan") or {}
    return "knowledge" if plan.get("need_retrieval", True) else "finalize"
```

- [ ] **Step 4: 运行测试确认通过**

Run:
```bash
uv run pytest tests/test_graph_routing.py -v
```
Expected: 3 个用例全 PASS。

- [ ] **Step 5: Commit**

```bash
git add app/agent/graph/nodes/coordinator.py tests/test_graph_routing.py
git commit -m "feat: 新增 Coordinator 条件路由函数"
```

---

## Task 4: build.py 接入 Coordinator 节点与条件边

图改为 `START → coordinator →(条件边)→ knowledge|finalize`，`knowledge → finalize → END`。

**Files:**
- Modify: `backend/app/agent/graph/build.py`
- Test: `backend/tests/test_graph_routing.py`（追加一个图结构集成测试）

- [ ] **Step 1: 写失败测试（追加到 test_graph_routing.py 末尾）**

在 `backend/tests/test_graph_routing.py` 末尾追加（验证：当 coordinator 判定不检索时，知识检索不被触发）。这里 patch 的是 `knowledge` 节点内部依赖的 `rag_service`（模块属性，稳定生效），而非节点函数本身——避免"函数引用已在 build 时绑定、patch 不生效"的陷阱：
```python
import pytest


@pytest.mark.asyncio
async def test_graph_skips_retrieval_when_no_retrieval(monkeypatch):
    """coordinator 判定 need_retrieval=False 时，图不应触发知识检索。"""
    import app.agent.graph.nodes.coordinator as co
    import app.agent.graph.nodes.knowledge as kn
    import app.agent.graph.nodes.finalize as fz

    class _Msg:
        def __init__(self, c):
            self.content = c

    async def _fake_coord_invoke(_messages):
        return _Msg('{"task_type": "knowledge_qa", "need_retrieval": false, "reason": "闲聊"}')

    async def _fake_final_invoke(_messages):
        return _Msg("你好，我能帮你查询企业知识。")

    rag_called = {"hit": False}

    async def _fake_get_docs(query, filter_meta=None):
        rag_called["hit"] = True
        return {"documents": [], "citations": [], "summary": "", "error": None}

    class _FakeCoordModel:
        ainvoke = staticmethod(_fake_coord_invoke)

    class _FakeFinalModel:
        ainvoke = staticmethod(_fake_final_invoke)

    monkeypatch.setattr(co, "chat_model", _FakeCoordModel())
    monkeypatch.setattr(fz, "chat_model", _FakeFinalModel())
    monkeypatch.setattr(kn.rag_service, "get_documents_for_agent", _fake_get_docs)

    from app.agent.graph.build import build_graph
    graph = build_graph()
    result = await graph.ainvoke({"query": "你好啊", "history": [], "trace": []})

    assert rag_called["hit"] is False                 # 检索未被触发
    assert result["plan"]["need_retrieval"] is False
    assert result["final_answer"] == "你好，我能帮你查询企业知识。"
```

> 说明：即便条件边把流程导向 finalize 时 knowledge 节点未执行，patch `rag_service` 也是最稳的断言锚点——检索没发生，`rag_called["hit"]` 必为 False。这比 patch 节点函数引用可靠。

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
uv run pytest tests/test_graph_routing.py::test_graph_skips_knowledge_when_no_retrieval -v
```
Expected: FAIL（当前图无 coordinator，`START` 直接进 knowledge，`plan` 不存在）。

- [ ] **Step 3: 改 build.py**

修改 `backend/app/agent/graph/build.py` 为：
```python
from langgraph.graph import StateGraph, START, END

from app.agent.graph.state import AgentState
from app.agent.graph.nodes.coordinator import coordinator_node, route_after_coordinator
from app.agent.graph.nodes.finalize import finalize_node
from app.agent.graph.nodes.knowledge import knowledge_node


def build_graph():
    """Phase 3 图：START → coordinator →(条件边)→ knowledge|finalize；knowledge → finalize → END。"""
    g = StateGraph(AgentState)
    g.add_node("coordinator", coordinator_node)
    g.add_node("knowledge", knowledge_node)
    g.add_node("finalize", finalize_node)

    g.add_edge(START, "coordinator")
    g.add_conditional_edges(
        "coordinator",
        route_after_coordinator,
        {"knowledge": "knowledge", "finalize": "finalize"},
    )
    g.add_edge("knowledge", "finalize")
    g.add_edge("finalize", END)
    return g.compile()
```

- [ ] **Step 4: 运行测试确认通过**

Run:
```bash
uv run pytest tests/test_graph_routing.py -v
```
Expected: 全部 PASS（含路由单测 + 集成测试；若集成测试按 Step 1 注释被 skip，则其余全 PASS 且该用例 skipped）。

- [ ] **Step 5: 行尾核查 + Commit**

Run:
```bash
git diff --stat app/agent/graph/build.py
git diff --stat --ignore-all-space app/agent/graph/build.py
```
（build.py 是 Phase 2 新建文件，通常为 LF，无污染风险；若两者差距大则按 Task 1 Step 3 的 PowerShell 方式修回。）
```bash
git add app/agent/graph/build.py tests/test_graph_routing.py
git commit -m "feat: 图接入 Coordinator 节点与条件路由"
```

---

## Task 5: runner 初始 plan 展示 + 端到端验证

让前端进度区显示"识别任务类型"步骤；初始 state 补 `plan` 键；端到端真实验证 coordinator 分类 + 路由。

**Files:**
- Modify: `backend/app/agent/graph/runner.py`

- [ ] **Step 1: 改 runner.py 的 `_initial_plan` 与初始 state**

修改 `backend/app/agent/graph/runner.py`：

把 `_initial_plan` 函数改为（在最前面加一个"识别任务类型"步骤，其 id 与 coordinator 发的 step 一致）：
```python
def _initial_plan() -> list:
    return [
        {"id": "task_understood", "title": "识别任务类型", "status": "todo", "level": "muted"},
        {"id": "answer_generated", "title": "生成最终回答", "status": "todo", "level": "muted"},
    ]
```

把 `stream` 方法里构建 `state` 的字典补上 `plan` 键（其余不变）：
```python
        state = {
            "query": query,
            "history": history or [],
            "identity": identity,
            "plan": {},
            "documents": [],
            "citations": [],
            "trace": [],
        }
```

- [ ] **Step 2: 跑 runner 既有测试确认未破坏**

Run:
```bash
uv run pytest tests/test_graph_runner_sse.py -v
```
Expected: 2 个既有用例仍全 PASS（runner 的对外事件 schema 未变）。

- [ ] **Step 3: 全量回归**

Run:
```bash
uv run pytest tests/ -q
```
Expected: 全部 PASS（既有契约测试 + 全部 graph 测试，含本 Phase 新增的 coordinator/routing 测试）。任何失败原样贴报告。

- [ ] **Step 4: 端到端真实验证（controller 执行，非 subagent）**

> 此步由控制者用临时脚本真实运行后删除，验证 coordinator 真实分类 + 路由 + token 不泄漏。subagent 实现到 Step 3 即可，把 Step 4 留给控制者。

临时脚本 `backend/_tmp_phase3_verify.py`（验证后删除）：
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
    print(" 出现任务识别:", "task_understood" in step_ids)
    print(" 出现知识检索:", "tool_rag_summary_tools" in step_ids)
    print(" 回答前60字:", tokens[:60])


async def main():
    await run("公司的年假制度是什么")   # 期望走检索
    await run("你好")                    # 可能不走检索（取决于模型分类）


if __name__ == "__main__":
    asyncio.run(main())
```
运行：`PYTHONPATH=<backend绝对路径> uv run python _tmp_phase3_verify.py`
预期：两个 query 都出现 `task_understood` 步骤；走检索的 query 还出现 `tool_rag_summary_tools`；回答 token 干净（不含分类 JSON、不含 HyDE 假设文档）。验证后删除临时脚本。

- [ ] **Step 5: Commit（仅 runner 改动）**

```bash
git diff --stat app/agent/graph/runner.py
git diff --stat --ignore-all-space app/agent/graph/runner.py
git add app/agent/graph/runner.py
git commit -m "feat: GraphRunner 展示任务识别步骤并初始化 plan"
```

---

## 后续计划（不在本计划范围）

- **Phase 4：** Task 节点 + 三个 tool（`tools/compare_tool.py`、`report_tool.py`、`form_tool.py`），coordinator 按 `task_type` 分流到 Task 节点。
- **Phase 5：** KnowledgeGap 节点 + `knowledge_gaps` 表 + API + 前端缺口页（`is_enough=False` 触发）。
- **Phase 6：** `agent_traces` 表落库（trace 已在 state 中累积，落库即可）。
- **Phase 7：** 默认引擎切换为 graph，旧 AgentLoop 保留 env 开关回退。
