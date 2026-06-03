# LangGraph 流式桥接 Spike + Knowledge 节点接入 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改动对外 SSE 契约的前提下，用 LangGraph 跑通"检索 → 生成最终回答"的最小图，验证流式桥接可行，并让现有 RAG 问答运行在 LangGraph 编排之上。

**Architecture:** 新建 `GraphRunner.stream()`，它消费 `graph.astream(stream_mode=["messages","custom"])` 的输出，翻译成与现有 `AgentLoop.stream()` **完全相同 schema** 的内部事件字典（`token`/`agent_plan`/`agent_step_update`/`step`/`done`）。这样对外函数 `get_agent_stream_response` 仅按一个环境变量开关选择引擎，SSE 协议零改动、前端无感知、现有契约测试自动适用。

**Tech Stack:** Python 3.12, LangGraph (uv 管理), langchain-core 1.2.x, ChatTongyi/ChatOllama (现有 `chat_model`), FastAPI SSE, pytest + pytest-asyncio。

**关于本计划范围：** 这是设计文档 `docs/design/2026-06-03-multi-agent-langgraph-design.md` 第 8 节渐进步骤的 **Phase 1 + Phase 2**。它是整个多 Agent 框架的风险闸门：跑通后 `astream` 的真实返回形态、metadata 过滤方式都成为已知事实，届时再写覆盖 Coordinator / Task / KnowledgeGap / agent_trace 的第二份计划。本计划完成即产出可工作软件（LangGraph 上跑通 RAG 问答 + 现有契约测试全绿）。

**所有命令在 `backend/` 目录下用 `uv run` 执行。** 例如 `cd backend` 后再运行 `uv run pytest ...`。

---

## 文件结构

新建：
- `backend/app/agent/graph/__init__.py` — 包导出
- `backend/app/agent/graph/state.py` — `AgentState` TypedDict
- `backend/app/agent/graph/nodes/__init__.py`
- `backend/app/agent/graph/nodes/finalize.py` — Finalize 节点（流式生成最终回答）
- `backend/app/agent/graph/nodes/knowledge.py` — Knowledge 节点（复用 rag_service）
- `backend/app/agent/graph/build.py` — `StateGraph` 组装
- `backend/app/agent/graph/stream_bridge.py` — `astream` → 现有内部事件字典翻译
- `backend/app/agent/graph/runner.py` — `GraphRunner.stream()` 对外入口（与 `AgentLoop.stream()` 同 schema）
- `backend/scripts/spike_astream_shape.py` — 一次性探测脚本（探明 astream 真实返回形态）
- `backend/tests/test_graph_finalize_node.py`
- `backend/tests/test_graph_stream_bridge.py`
- `backend/tests/test_graph_runner_sse.py`
- `backend/tests/test_graph_knowledge_node.py`
- `backend/tests/test_graph_knowledge_permission.py`

修改：
- `backend/app/agent/agent.py` — `get_agent_stream_response` 增加引擎开关（`AGENT_ENGINE`）
- `backend/pyproject.toml` — 增加 `langgraph` 主库依赖

---

# Phase 1 — 流式桥接 Spike

## Task 1: 安装 langgraph 并探明 astream 真实返回形态

**Files:**
- Modify: `backend/pyproject.toml`（dependencies 列表）
- Create: `backend/scripts/spike_astream_shape.py`

> 这是 spike 的探测核心：LangGraph 多 `stream_mode` 的返回形态（元组 `(mode, payload)` 还是 StreamPart `{"type","data"}`）随版本不同，必须先用最小图打印出来，后续桥接代码据此编写，不靠猜。

- [ ] **Step 1: 安装 langgraph 主库**

Run（在 `backend/` 目录）:
```bash
uv add langgraph
```
Expected: `pyproject.toml` 的 `dependencies` 出现 `langgraph>=...`，`uv.lock` 更新，无解析冲突。

- [ ] **Step 2: 编写探测脚本**

Create `backend/scripts/spike_astream_shape.py`:
```python
"""一次性探测脚本：打印 LangGraph astream 在多 stream_mode 下的真实返回形态。

运行： uv run python scripts/spike_astream_shape.py
目的： 确认 (a) 多模式下每次迭代产出的结构；(b) messages 模式里 metadata 含哪些键
      （尤其 langgraph_node，用于在 bridge 中过滤只放行 finalize 的 token）。
"""
import asyncio
from typing import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.config import get_stream_writer

from app.utils.factory import chat_model


class _State(TypedDict):
    query: str
    answer: str


async def _finalize(state: _State):
    writer = get_stream_writer()
    writer({"kind": "step", "phase": "finalize_start"})
    # 真实走一次流式 LLM，确认 messages 模式能捕获其 token
    msg = await chat_model.ainvoke(f"用一句话回答：{state['query']}")
    return {"answer": msg.content}


def _build():
    g = StateGraph(_State)
    g.add_node("finalize", _finalize)
    g.add_edge(START, "finalize")
    g.add_edge("finalize", END)
    return g.compile()


async def main():
    graph = _build()
    print("=== 开始探测 astream(stream_mode=['messages','custom']) ===")
    async for item in graph.astream(
        {"query": "你好"},
        stream_mode=["messages", "custom"],
    ):
        print("REPR:", repr(item)[:300])
        print("TYPE:", type(item))
        print("-" * 40)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: 运行探测脚本并记录形态**

Run（在 `backend/` 目录，需已配置 `.env` 的 LLM 凭据）:
```bash
uv run python scripts/spike_astream_shape.py
```
Expected: 打印出每次迭代的结构。**把观察到的形态记录到本任务下方注释里**，后续桥接以此为准。预期两种之一：
- 元组形态：`('messages', (AIMessageChunk(...), {'langgraph_node': 'finalize', ...}))` 与 `('custom', {'kind': 'step', ...})`
- StreamPart 形态：`{'type': 'messages', 'data': (...)}` 与 `{'type': 'custom', 'data': {...}}`

确认 messages 项的 metadata 字典里含 `langgraph_node` 键且值为 `"finalize"`。

- [ ] **Step 4: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/scripts/spike_astream_shape.py
git commit -m "chore: 引入 langgraph 并探明 astream 多模式返回形态"
```

---

## Task 2: 定义 AgentState

**Files:**
- Create: `backend/app/agent/graph/__init__.py`（空文件）
- Create: `backend/app/agent/graph/state.py`

- [ ] **Step 1: 写 state.py**

Create `backend/app/agent/graph/state.py`:
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

    # Knowledge 产出
    documents: list                     # list[str]
    citations: list                     # list[dict]，复用现有 citations 结构
    is_enough: bool

    # 输出
    final_answer: str

    # 轨迹（append-only）
    trace: Annotated[list, operator.add]
```

- [ ] **Step 2: 建空 __init__.py**

Create `backend/app/agent/graph/__init__.py` 内容为空。

- [ ] **Step 3: 验证可导入**

Run（在 `backend/` 目录）:
```bash
uv run python -c "from app.agent.graph.state import AgentState; print('ok')"
```
Expected: 打印 `ok`，无导入错误。

- [ ] **Step 4: Commit**

```bash
git add backend/app/agent/graph/__init__.py backend/app/agent/graph/state.py
git commit -m "feat: 新增 LangGraph AgentState 定义"
```

---

## Task 3: Finalize 节点

Finalize 节点基于 `state["documents"]`（Phase 1 暂为空列表）和 `query` 调用 `chat_model` 生成最终回答；并通过 `get_stream_writer()` 发一条 step 事件。

**Files:**
- Create: `backend/app/agent/graph/nodes/__init__.py`（空文件）
- Create: `backend/app/agent/graph/nodes/finalize.py`
- Test: `backend/tests/test_graph_finalize_node.py`

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_graph_finalize_node.py`:
```python
import pytest

from app.agent.graph import nodes as _nodes_pkg  # noqa: F401 确保包存在
from app.agent.graph.nodes.finalize import finalize_node


class _FakeMsg:
    def __init__(self, content):
        self.content = content


@pytest.mark.asyncio
async def test_finalize_node_returns_final_answer(monkeypatch):
    async def _fake_ainvoke(_messages):
        return _FakeMsg("这是最终回答")

    import app.agent.graph.nodes.finalize as fz
    monkeypatch.setattr(fz.chat_model, "ainvoke", _fake_ainvoke)

    state = {"query": "公司年假制度是什么", "documents": [], "history": []}
    update = await finalize_node(state)

    assert update["final_answer"] == "这是最终回答"
    assert isinstance(update["trace"], list)
    assert update["trace"][0]["agent"] == "finalize"
```

- [ ] **Step 2: 运行测试确认失败**

Run（在 `backend/` 目录）:
```bash
uv run pytest tests/test_graph_finalize_node.py -v
```
Expected: FAIL，`ModuleNotFoundError: app.agent.graph.nodes.finalize`。

- [ ] **Step 3: 实现 finalize 节点**

Create `backend/app/agent/graph/nodes/__init__.py` 内容为空。

Create `backend/app/agent/graph/nodes/finalize.py`:
```python
from langgraph.config import get_stream_writer

from app.agent.graph.state import AgentState
from app.utils.factory import chat_model
from app.utils.prompt_loader import load_prompt

_SYSTEM_PROMPT = load_prompt("main_prompt")


def _build_messages(state: AgentState) -> list:
    documents = state.get("documents") or []
    if documents:
        context = "\n\n".join(f"【文档片段{i}】\n{d}" for i, d in enumerate(documents, 1))
        user = (
            f"请只基于以下检索到的文档片段回答用户问题；"
            f"若片段不足以回答，请明确说明知识库信息不足。\n\n"
            f"{context}\n\n用户问题：{state['query']}"
        )
    else:
        user = state["query"]
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


async def finalize_node(state: AgentState) -> dict:
    """生成最终回答。token 由 LangGraph messages 模式自动流出（节点名 finalize）。"""
    writer = get_stream_writer()
    writer({"kind": "step", "id": "answer_generated", "status": "running",
            "level": "info", "detail": "正在生成最终回答", "title": "生成最终回答"})

    messages = _build_messages(state)
    msg = await chat_model.ainvoke(messages)
    answer = msg.content if hasattr(msg, "content") else str(msg)

    return {
        "final_answer": answer,
        "trace": [{"agent": "finalize", "status": "done", "output": answer[:200]}],
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run（在 `backend/` 目录）:
```bash
uv run pytest tests/test_graph_finalize_node.py -v
```
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/graph/nodes/__init__.py backend/app/agent/graph/nodes/finalize.py backend/tests/test_graph_finalize_node.py
git commit -m "feat: 新增 LangGraph Finalize 节点"
```

---

## Task 4: stream_bridge — astream 输出翻译成现有内部事件字典

bridge 把 `graph.astream` 的输出翻译成与 `AgentLoop.stream()` 完全相同 schema 的事件字典。

> **依赖 Task 1 探测结果**：下面代码默认 astream 多模式返回 **元组 `(mode, payload)`**（LangGraph 多 stream_mode 的标准形态）。若 Task 1 观察到的是 StreamPart `{"type","data"}` 形态，则把 `_iter_stream` 内的解包改为 `mode, payload = item["type"], item["data"]`。

**Files:**
- Create: `backend/app/agent/graph/stream_bridge.py`
- Test: `backend/tests/test_graph_stream_bridge.py`

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_graph_stream_bridge.py`:
```python
import pytest

from app.agent.graph.stream_bridge import translate_stream_item


class _Chunk:
    def __init__(self, content):
        self.content = content


def test_translate_finalize_token():
    item = ("messages", (_Chunk("答案片段"), {"langgraph_node": "finalize"}))
    events = list(translate_stream_item(item))
    assert events == [{"type": "token", "data": "答案片段"}]


def test_translate_drops_non_finalize_token():
    # HyDE / Knowledge 内部 LLM 的 token 不应泄漏给用户
    item = ("messages", (_Chunk("假设性文档"), {"langgraph_node": "knowledge"}))
    assert list(translate_stream_item(item)) == []


def test_translate_empty_token_ignored():
    item = ("messages", (_Chunk(""), {"langgraph_node": "finalize"}))
    assert list(translate_stream_item(item)) == []


def test_translate_custom_step_event():
    item = ("custom", {"kind": "step", "id": "answer_generated",
                       "status": "running", "level": "info", "detail": "正在生成最终回答"})
    events = list(translate_stream_item(item))
    assert events == [{
        "type": "agent_step_update",
        "data": {"id": "answer_generated", "status": "running",
                 "level": "info", "detail": "正在生成最终回答"},
    }]


def test_translate_unknown_custom_ignored():
    item = ("custom", {"kind": "debug", "msg": "noise"})
    assert list(translate_stream_item(item)) == []
```

- [ ] **Step 2: 运行测试确认失败**

Run（在 `backend/` 目录）:
```bash
uv run pytest tests/test_graph_stream_bridge.py -v
```
Expected: FAIL，`ModuleNotFoundError: app.agent.graph.stream_bridge`。

- [ ] **Step 3: 实现 stream_bridge**

Create `backend/app/agent/graph/stream_bridge.py`:
```python
"""把 LangGraph astream 的输出翻译成与 AgentLoop.stream() 相同 schema 的事件字典。

事件 schema（对齐 app/agent/agent.py 的内部事件）：
  {"type": "token", "data": str}
  {"type": "agent_step_update", "data": {...}}
"""
from typing import Iterator

# 只放行该节点产生的 LLM token 给用户；其余节点（knowledge 内的 HyDE 等）token 丢弃
_USER_FACING_LLM_NODE = "finalize"

# custom 事件里允许翻译成 step_update 的字段
_STEP_FIELDS = ("id", "status", "level", "detail", "title")


def translate_stream_item(item) -> Iterator[dict]:
    """翻译单个 astream 产出项。返回 0..N 个内部事件字典。"""
    # 多 stream_mode 标准形态：(mode, payload) 元组
    mode, payload = item

    if mode == "messages":
        message_chunk, metadata = payload
        if metadata.get("langgraph_node") != _USER_FACING_LLM_NODE:
            return
        content = getattr(message_chunk, "content", "") or ""
        if content:
            yield {"type": "token", "data": content}
        return

    if mode == "custom":
        if not isinstance(payload, dict) or payload.get("kind") != "step":
            return
        data = {k: payload[k] for k in _STEP_FIELDS if k in payload}
        yield {"type": "agent_step_update", "data": data}
        return
```

- [ ] **Step 4: 运行测试确认通过**

Run（在 `backend/` 目录）:
```bash
uv run pytest tests/test_graph_stream_bridge.py -v
```
Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/graph/stream_bridge.py backend/tests/test_graph_stream_bridge.py
git commit -m "feat: 新增 LangGraph 流式桥接（astream → 现有事件 schema）"
```

---

## Task 5: build.py 组装最小图 + GraphRunner.stream()

`GraphRunner.stream()` 产出与 `AgentLoop.stream()` 相同 schema 的事件序列：开头一个 `agent_plan`，中间 `token`/`agent_step_update`，结尾一个 `done`（含 steps/tokens/citations）。

**Files:**
- Create: `backend/app/agent/graph/build.py`
- Create: `backend/app/agent/graph/runner.py`
- Test: `backend/tests/test_graph_runner_sse.py`

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_graph_runner_sse.py`:
```python
import pytest

from app.agent.graph.runner import GraphRunner


async def _fake_astream(state, stream_mode=None):
    class _Chunk:
        def __init__(self, c):
            self.content = c
    yield ("custom", {"kind": "step", "id": "answer_generated",
                      "status": "running", "level": "info", "detail": "正在生成最终回答"})
    yield ("messages", (_Chunk("最终"), {"langgraph_node": "finalize"}))
    yield ("messages", (_Chunk("回答"), {"langgraph_node": "finalize"}))


@pytest.mark.asyncio
async def test_graph_runner_emits_same_schema_as_agentloop(monkeypatch):
    runner = GraphRunner()

    class _FakeGraph:
        def astream(self, state, stream_mode=None):
            return _fake_astream(state, stream_mode=stream_mode)

    monkeypatch.setattr(runner, "_graph", _FakeGraph())

    events = [e async for e in runner.stream("年假制度", history=[], identity=None)]
    types = [e["type"] for e in events]

    # 开头 agent_plan，结尾 done
    assert types[0] == "agent_plan"
    assert types[-1] == "done"
    # 中间有 token，且拼接为完整回答
    tokens = "".join(e["data"] for e in events if e["type"] == "token")
    assert tokens == "最终回答"
    # done 帧字段齐全
    done = events[-1]
    assert "steps" in done and "tokens" in done and "citations" in done
```

- [ ] **Step 2: 运行测试确认失败**

Run（在 `backend/` 目录）:
```bash
uv run pytest tests/test_graph_runner_sse.py -v
```
Expected: FAIL，`ModuleNotFoundError: app.agent.graph.runner`。

- [ ] **Step 3: 实现 build.py**

Create `backend/app/agent/graph/build.py`:
```python
from langgraph.graph import StateGraph, START, END

from app.agent.graph.state import AgentState
from app.agent.graph.nodes.finalize import finalize_node


def build_graph():
    """Phase 1 最小图：START → finalize → END。

    后续 Phase 在此基础上加 knowledge / coordinator / task 节点与条件边。
    """
    g = StateGraph(AgentState)
    g.add_node("finalize", finalize_node)
    g.add_edge(START, "finalize")
    g.add_edge("finalize", END)
    return g.compile()
```

- [ ] **Step 4: 实现 runner.py**

Create `backend/app/agent/graph/runner.py`:
```python
from typing import AsyncGenerator, Optional

from app.agent.graph.build import build_graph
from app.agent.graph.stream_bridge import translate_stream_item
from app.utils.auth_utils import RequestIdentity


def _initial_plan() -> list:
    return [
        {"id": "task_understood", "title": "理解用户问题", "status": "done", "level": "success"},
        {"id": "answer_generated", "title": "生成最终回答", "status": "todo", "level": "muted"},
    ]


class GraphRunner:
    """LangGraph 编排入口。stream() 产出与 AgentLoop.stream() 相同 schema 的事件。"""

    def __init__(self):
        self._graph = build_graph()

    async def stream(
        self, query: str, history: list = None, identity: Optional[RequestIdentity] = None
    ) -> AsyncGenerator[dict, None]:
        yield {"type": "agent_plan", "data": _initial_plan()}

        state = {
            "query": query,
            "history": history or [],
            "identity": identity,
            "documents": [],
            "citations": [],
            "trace": [],
        }

        full_answer: list[str] = []
        async for item in self._graph.astream(state, stream_mode=["messages", "custom"]):
            for event in translate_stream_item(item):
                if event["type"] == "token":
                    full_answer.append(event["data"])
                yield event

        yield {
            "type": "agent_step_update",
            "data": {"id": "answer_generated", "status": "done",
                     "level": "success", "detail": "已生成最终回答", "title": "生成最终回答"},
        }
        yield {"type": "done", "steps": [], "tokens": 0, "citations": []}


# 全局单例（图编译一次复用）
graph_runner = GraphRunner()
```

- [ ] **Step 5: 运行测试确认通过**

Run（在 `backend/` 目录）:
```bash
uv run pytest tests/test_graph_runner_sse.py -v
```
Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add backend/app/agent/graph/build.py backend/app/agent/graph/runner.py backend/tests/test_graph_runner_sse.py
git commit -m "feat: 组装 LangGraph 最小图与 GraphRunner（对齐 AgentLoop 事件 schema）"
```

---

## Task 6: 接入 get_agent_stream_response（环境变量开关）

让对外 SSE 函数按 `AGENT_ENGINE` 选择引擎，默认仍是旧 `loop`，可切 `graph`。SSE 协议零改动。

**Files:**
- Modify: `backend/app/agent/agent.py`（`get_agent_stream_response` 内的 `agent_loop.stream(...)` 调用处，约 473 行）

- [ ] **Step 1: 定位现有调用**

`backend/app/agent/agent.py` 第 473 行附近：
```python
    async for event in agent_loop.stream(query, history, identity=identity):
```

- [ ] **Step 2: 改为按开关选择引擎**

在文件顶部 import 区加：
```python
from app.agent.graph.runner import graph_runner
```

把上面那行替换为：
```python
    engine = os.getenv("AGENT_ENGINE", "loop").strip().lower()
    if engine == "graph":
        event_source = graph_runner.stream(query, history, identity=identity)
    else:
        event_source = agent_loop.stream(query, history, identity=identity)

    async for event in event_source:
```

- [ ] **Step 3: 运行现有契约测试确认未破坏（默认 loop 引擎）**

Run（在 `backend/` 目录）:
```bash
uv run pytest tests/test_agent_sse_steps.py tests/test_agent_rag_generation_mode.py -v
```
Expected: 全部 PASS（默认 `AGENT_ENGINE=loop`，行为与改动前一致）。

- [ ] **Step 4: 用 graph 引擎跑契约测试**

> `test_agent_sse_steps.py` 用 monkeypatch 替换 `agent.agent_loop.stream`，不覆盖 graph 引擎路径，因此这里仅验证默认路径不破坏即可。graph 路径由 Task 5 的 runner 测试 + Task 7 的端到端手动验证覆盖。

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/agent.py
git commit -m "feat: get_agent_stream_response 增加 AGENT_ENGINE 引擎开关"
```

---

## Task 7: 端到端手动验证（spike 验收闸门）

> 这是判定方案 B 可行性的关键一步：真实起服务，用 `AGENT_ENGINE=graph` 让前端走 LangGraph，确认 token 正常逐字显示、进度步骤正常、无中间节点 token 泄漏。

**Files:** 无（手动验证）

- [ ] **Step 1: 以 graph 引擎启动后端**

在 `backend/` 目录设置环境变量后启动（PowerShell）：
```powershell
$env:AGENT_ENGINE = "graph"
uv run uvicorn main:app --port 8000
```
（前端按项目 start-project 流程在 3000 端口启动。）

- [ ] **Step 2: 在前端聊天页提问并观察**

发送一条普通问题（如"你好，介绍一下你自己"）。
Expected:
- 回答逐字流式显示（token 流正常）。
- 进度区出现"生成最终回答"步骤并由 running → done。
- 无异常的中间内容泄漏（无 HyDE/假设性文档片段混入回答）。
- 浏览器 Network 里 SSE 帧格式与旧引擎一致（`data: {"type":"response",...}` 等）。

- [ ] **Step 3: 记录 spike 结论**

在本任务下方写一行结论：`spike 通过 / 不通过 + 原因`。
- **通过** → 进入 Phase 2。
- **不通过** → 回到 Task 4，依据观察到的 astream 形态/metadata 修正 bridge；若 messages 模式无法稳定区分节点，评估改用 `astream_events(version="v2")` 按 `event=="on_chat_model_stream"` + `metadata["langgraph_node"]` 过滤（备选桥接路径）。

---

# Phase 2 — Knowledge 节点接入

## Task 8: Knowledge 节点（复用 rag_service，从 state 取 identity）

Knowledge 节点调用现有 `rag_service.get_documents_for_agent()`，带 `state["identity"]` 做权限过滤，把 documents/citations/is_enough 写回 state。

**Files:**
- Create: `backend/app/agent/graph/nodes/knowledge.py`
- Test: `backend/tests/test_graph_knowledge_node.py`

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_graph_knowledge_node.py`:
```python
import pytest

from app.agent.graph.nodes.knowledge import knowledge_node
from app.utils.auth_utils import RequestIdentity


@pytest.mark.asyncio
async def test_knowledge_node_populates_documents_and_citations(monkeypatch):
    captured = {}

    async def _fake_get_docs(query, filter_meta=None):
        captured["filter_meta"] = filter_meta
        return {
            "documents": ["年假每年 5 天"],
            "citations": [{"filename": "制度.pdf", "score": 0.9}],
            "summary": "",
            "error": None,
        }

    async def _fake_filter(user_id, is_admin=False, dept_id=None):
        return {"user_id": user_id}

    import app.agent.graph.nodes.knowledge as kn
    monkeypatch.setattr(kn.rag_service, "get_documents_for_agent", _fake_get_docs)
    monkeypatch.setattr(kn.kb_service, "build_accessible_filter", _fake_filter)

    state = {"query": "年假几天", "identity": RequestIdentity(user_id="u1")}
    update = await knowledge_node(state)

    assert update["documents"] == ["年假每年 5 天"]
    assert update["citations"][0]["filename"] == "制度.pdf"
    assert update["is_enough"] is True
    # 权限过滤确实用了 identity
    assert captured["filter_meta"] == {"user_id": "u1"}


@pytest.mark.asyncio
async def test_knowledge_node_marks_not_enough_when_no_docs(monkeypatch):
    async def _fake_get_docs(query, filter_meta=None):
        return {"documents": [], "citations": [], "summary": "未找到", "error": None}

    async def _fake_filter(user_id, is_admin=False, dept_id=None):
        return None

    import app.agent.graph.nodes.knowledge as kn
    monkeypatch.setattr(kn.rag_service, "get_documents_for_agent", _fake_get_docs)
    monkeypatch.setattr(kn.kb_service, "build_accessible_filter", _fake_filter)

    state = {"query": "未知问题", "identity": RequestIdentity(user_id="u1")}
    update = await knowledge_node(state)

    assert update["documents"] == []
    assert update["is_enough"] is False
```

- [ ] **Step 2: 运行测试确认失败**

Run（在 `backend/` 目录）:
```bash
uv run pytest tests/test_graph_knowledge_node.py -v
```
Expected: FAIL，`ModuleNotFoundError: app.agent.graph.nodes.knowledge`。

- [ ] **Step 3: 实现 knowledge 节点**

Create `backend/app/agent/graph/nodes/knowledge.py`:
```python
from typing import Optional

from langgraph.config import get_stream_writer

from app.agent.graph.state import AgentState
from app.rag.rag_service import rag_service
from app.services.kb_service import kb_service
from app.utils.auth_utils import RequestIdentity


async def _build_filter(identity: Optional[RequestIdentity]):
    if not identity or not identity.user_id:
        return None
    return await kb_service.build_accessible_filter(
        identity.user_id, is_admin=identity.is_admin, dept_id=identity.dept_id
    )


async def knowledge_node(state: AgentState) -> dict:
    """检索知识依据。权限 identity 从 state 取，绝不走隐式传递。"""
    writer = get_stream_writer()
    writer({"kind": "step", "id": "tool_rag_summary_tools", "status": "running",
            "level": "info", "detail": "正在检索相关知识库", "title": "检索相关知识库"})

    identity = state.get("identity")
    filter_meta = await _build_filter(identity)
    result = await rag_service.get_documents_for_agent(state["query"], filter_meta=filter_meta)

    documents = result.get("documents", [])
    citations = result.get("citations", [])
    is_enough = bool(documents)

    writer({"kind": "step", "id": "tool_rag_summary_tools", "status": "done",
            "level": "success", "detail": f"已检索 {len(citations)} 个文档",
            "title": "已检索知识库"})

    return {
        "documents": documents,
        "citations": citations,
        "is_enough": is_enough,
        "trace": [{"agent": "knowledge", "status": "done",
                   "output": f"documents={len(documents)} is_enough={is_enough}"}],
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run（在 `backend/` 目录）:
```bash
uv run pytest tests/test_graph_knowledge_node.py -v
```
Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/graph/nodes/knowledge.py backend/tests/test_graph_knowledge_node.py
git commit -m "feat: 新增 LangGraph Knowledge 节点（复用 rag_service + 权限过滤）"
```

---

## Task 9: 图加入 Knowledge 节点 + GraphRunner 输出 citations

把图改成 `START → knowledge → finalize → END`，并让 GraphRunner 从最终 state 取 citations 放进 done 帧（根除 ContextVar 依赖）。

**Files:**
- Modify: `backend/app/agent/graph/build.py`
- Modify: `backend/app/agent/graph/runner.py`
- Test: `backend/tests/test_graph_runner_sse.py`（新增一条断言 citations 的用例）

- [ ] **Step 1: 写失败测试（在现有测试文件追加）**

设计：citations 由 Knowledge 节点写入 state，但 `astream(stream_mode=["messages","custom"])` 不产出终态。解决办法是给 `astream` 追加 `"values"` 模式——它每步产出全量 state 快照，runner 保留最后一次快照里的 `citations` 放进 done 帧。

在 `backend/tests/test_graph_runner_sse.py` 末尾追加：
```python
@pytest.mark.asyncio
async def test_graph_runner_done_carries_citations_from_state(monkeypatch):
    runner = GraphRunner()

    class _Chunk:
        def __init__(self, c):
            self.content = c

    async def _fake_astream(state, stream_mode=None):
        yield ("messages", (_Chunk("答"), {"langgraph_node": "finalize"}))
        yield ("values", {"citations": [{"filename": "a.pdf", "score": 0.8}],
                          "final_answer": "答"})

    class _FakeGraph:
        def astream(self, state, stream_mode=None):
            return _fake_astream(state, stream_mode=stream_mode)

    monkeypatch.setattr(runner, "_graph", _FakeGraph())

    events = [e async for e in runner.stream("q", history=[], identity=None)]
    done = events[-1]
    assert done["type"] == "done"
    assert done["citations"] == [{"filename": "a.pdf", "score": 0.8}]
```

- [ ] **Step 2: 运行测试确认失败**

Run（在 `backend/` 目录）:
```bash
uv run pytest tests/test_graph_runner_sse.py::test_graph_runner_done_carries_citations_from_state -v
```
Expected: FAIL（当前 runner 不处理 values，citations 为空）。

- [ ] **Step 3: 改 build.py 加入 knowledge 节点**

修改 `backend/app/agent/graph/build.py`：
```python
from langgraph.graph import StateGraph, START, END

from app.agent.graph.state import AgentState
from app.agent.graph.nodes.finalize import finalize_node
from app.agent.graph.nodes.knowledge import knowledge_node


def build_graph():
    """Phase 2 图：START → knowledge → finalize → END。"""
    g = StateGraph(AgentState)
    g.add_node("knowledge", knowledge_node)
    g.add_node("finalize", finalize_node)
    g.add_edge(START, "knowledge")
    g.add_edge("knowledge", "finalize")
    g.add_edge("finalize", END)
    return g.compile()
```

- [ ] **Step 4: 改 runner.py 用 values 模式捕获 citations**

修改 `backend/app/agent/graph/runner.py` 的 `stream` 方法：把 `stream_mode` 改为三模式并捕获 values 终态。

将 `async for item ...` 循环及其后的 done 帧替换为：
```python
        full_answer: list[str] = []
        final_citations: list = []
        async for item in self._graph.astream(
            state, stream_mode=["messages", "custom", "values"]
        ):
            mode, payload = item
            if mode == "values":
                # values 模式每步产出全量 state 快照，保留最后一次的 citations
                if isinstance(payload, dict) and payload.get("citations") is not None:
                    final_citations = payload["citations"]
                continue
            for event in translate_stream_item(item):
                if event["type"] == "token":
                    full_answer.append(event["data"])
                yield event

        yield {
            "type": "agent_step_update",
            "data": {"id": "answer_generated", "status": "done",
                     "level": "success", "detail": "已生成最终回答", "title": "生成最终回答"},
        }
        yield {"type": "done", "steps": [], "tokens": 0, "citations": final_citations}
```

> 注意：`translate_stream_item` 只认 `messages`/`custom`，`values` 项在 runner 里先行拦截，不会进入 bridge。

- [ ] **Step 5: 运行 runner 测试全绿**

Run（在 `backend/` 目录）:
```bash
uv run pytest tests/test_graph_runner_sse.py -v
```
Expected: 全部 PASS（含 citations 用例与原 schema 用例）。

- [ ] **Step 6: Commit**

```bash
git add backend/app/agent/graph/build.py backend/app/agent/graph/runner.py backend/tests/test_graph_runner_sse.py
git commit -m "feat: 图加入 Knowledge 节点，GraphRunner 经 values 模式输出 citations"
```

---

## Task 10: 权限回归测试 + 端到端验证

确认 identity 经 state 流转后，Knowledge 节点仍正确做权限过滤（防越权回归），并端到端确认 graph 引擎下 RAG 问答正常、引用来源正常。

**Files:**
- Test: `backend/tests/test_graph_knowledge_permission.py`

- [ ] **Step 1: 写权限测试**

Create `backend/tests/test_graph_knowledge_permission.py`:
```python
import pytest

from app.agent.graph.nodes.knowledge import knowledge_node
from app.utils.auth_utils import RequestIdentity


@pytest.mark.asyncio
async def test_identity_drives_permission_filter(monkeypatch):
    """非管理员用户的 user_id/dept_id 必须传进 build_accessible_filter。"""
    seen = {}

    async def _fake_filter(user_id, is_admin=False, dept_id=None):
        seen.update(user_id=user_id, is_admin=is_admin, dept_id=dept_id)
        return {"scoped": True}

    async def _fake_get_docs(query, filter_meta=None):
        seen["filter_meta"] = filter_meta
        return {"documents": ["x"], "citations": [], "summary": "", "error": None}

    import app.agent.graph.nodes.knowledge as kn
    monkeypatch.setattr(kn.kb_service, "build_accessible_filter", _fake_filter)
    monkeypatch.setattr(kn.rag_service, "get_documents_for_agent", _fake_get_docs)

    identity = RequestIdentity(user_id="u9", is_admin=False, dept_id="d3")
    await knowledge_node({"query": "q", "identity": identity})

    assert seen["user_id"] == "u9"
    assert seen["is_admin"] is False
    assert seen["dept_id"] == "d3"
    assert seen["filter_meta"] == {"scoped": True}


@pytest.mark.asyncio
async def test_missing_identity_yields_no_filter(monkeypatch):
    """无 identity 时 filter_meta 为 None（与现有 agent_tools 行为一致）。"""
    seen = {}

    async def _fake_get_docs(query, filter_meta=None):
        seen["filter_meta"] = filter_meta
        return {"documents": [], "citations": [], "summary": "", "error": None}

    import app.agent.graph.nodes.knowledge as kn
    monkeypatch.setattr(kn.rag_service, "get_documents_for_agent", _fake_get_docs)

    await knowledge_node({"query": "q", "identity": None})
    assert seen["filter_meta"] is None
```

- [ ] **Step 2: 运行权限测试**

Run（在 `backend/` 目录）:
```bash
uv run pytest tests/test_graph_knowledge_permission.py -v
```
Expected: 全部 PASS。

- [ ] **Step 3: 全量回归（确认未破坏既有契约）**

Run（在 `backend/` 目录）:
```bash
uv run pytest tests/ -v
```
Expected: 全部 PASS，尤其 `test_agent_sse_steps.py`、`test_kb_permissions.py`、`test_agent_rag_generation_mode.py`。

- [ ] **Step 4: 端到端验证 graph 引擎下的 RAG 问答**

以 `AGENT_ENGINE=graph` 启动后端（同 Task 7 Step 1），上传一份文档后提一个能命中知识库的问题。
Expected:
- 回答基于检索内容、逐字流式显示。
- 进度区依次出现"检索相关知识库 → 已检索 N 个文档 → 生成最终回答"。
- `done` 帧 citations 非空、前端引用来源正常展示（验证 ContextVar 老坑已根除）。

- [ ] **Step 5: 记录 Phase 2 结论**

在本任务下方记录：`Phase 2 通过 / 问题`。通过即可着手第二份计划（Coordinator / Task / KnowledgeGap / agent_trace）。

---

## 后续计划（不在本计划范围，待 spike 通过后展开为独立计划）

以下是设计文档 §8 的 Phase 3–7，依赖本计划已探明的 `astream` 形态与桥接方式，将各自成为独立的 bite-sized 计划：

- **Phase 3：Coordinator 路由节点 + AgentState 扩展**（`plan` 字段、`add_conditional_edges` 路由、简单 `knowledge_qa` 短路）
- **Phase 4：Task 节点 + 三个 tool**（`tools/compare_tool.py`、`report_tool.py`、`form_tool.py`）
- **Phase 5：KnowledgeGap 节点 + `knowledge_gaps` 表 + API + 前端缺口页**
- **Phase 6：`agent_traces` 表落库**
- **Phase 7：默认引擎切换为 graph，旧 AgentLoop 保留 env 开关回退**
