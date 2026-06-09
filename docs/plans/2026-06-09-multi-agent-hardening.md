# 多 Agent 图加固与优化 实施计划

> **执行者须知（适用于任意能读写文件、运行命令的 AI 编码 agent —— Claude Code / Codex / Cursor 等均可）：** 本计划自包含，不依赖任何特定工具的私有能力或对话上下文。每个 Task 都给出确切文件路径、可直接套用的测试与实现代码、确切命令与预期输出。**按 Task 编号顺序逐个执行**；每个含代码改动的 Task 内部严格走 TDD：先写失败测试 → 运行确认失败 → 写实现 → 运行确认通过 → 行尾核查 → commit。除非某 Task 显式标注「需用户确认」，否则连续执行、无需中途征求确认。Steps 用 `- [ ]` 复选框便于逐项勾选跟踪。先通读下面的「执行约定」再开始。

**Goal:** 把现有 LangGraph 多 agent 图从「能跑的单向流水线」加固成「正确、健壮、可观测」的形态，修掉三处确凿隐患（多轮历史丢失、节点异常断流、token 漏算），补齐 trace 落库，并为真正的协同能力（Critic 回路 / 规划器）立好设计入口。

**Architecture:** 不改对外 SSE 契约、不改图的节点划分，只在节点内部与 `runner`/`state` 层做加固。Phase 1 是确定性修复（直接 TDD）；Phase 2 是工程加固（trace 落库 + 对 #4 做工程评估）；Phase 3 是架构升级（Critic 回路 + Coordinator 规划器），它是开放设计，**实现前必须先做需求/方案探索并产出独立的实施计划**，本计划只锁定方向与决策点，不写实现步骤。

**Tech Stack:** Python 3.12, LangGraph（`StateGraph` / `astream` 多 stream_mode）, langchain-core, `ChatTongyi`(阿里云百炼)/`ChatOllama`, SQLAlchemy async（`AsyncSessionLocal` + `create_all`）, pytest + pytest-asyncio。

**所有命令在 `backend/` 目录下用 `uv run` 执行。** 修改既有文件后必做行尾核查（`git diff --stat` vs `--ignore-all-space`，差距大则用 PowerShell 转回 CRLF，见每个 Task 的核查步骤）。新建文件无需核查。

**前置（已在 master）：** `app/agent/graph/` 下 `state.py`/`build.py`/`runner.py`/`stream_bridge.py`/`_stream.py` + `nodes/`（coordinator/knowledge/task/knowledge_gap/finalize）已实现并跑通；对外出口 `get_agent_stream_response`（`app/agent/agent.py`）通过 `AGENT_ENGINE=graph` 切到 `graph_runner`。

---

## 执行约定（环境与纪律，任意执行者先读）

- **仓库根**：本计划路径相对仓库根为 `docs/plans/2026-06-09-multi-agent-hardening.md`；后端代码在 `backend/`，前端在 `front/`，本计划只动 `backend/`。
- **工作目录**：除非某步另有说明，所有命令均在 `backend/` 目录下执行。
- **运行器**：统一用 `uv run <cmd>`（如 `uv run pytest ...`、`uv run python ...`）。若环境无 `uv`，等价改用项目虚拟环境的 `python -m pytest`。`pyproject.toml` 的 `venv.path` warning 无害，忽略。
- **平台**：开发机为 Windows + PowerShell，行尾核查步骤中的 PowerShell 片段按此假设。**核心约束是「修改既有文件时不要把整个文件的行尾从 CRLF 翻成 LF」**——很多编辑器/工具会在写入时统一成 LF，导致 `git diff` 把整文件每行都算作改动。若在非 Windows 平台执行，用等效手段（如 `dos2unix`/`unix2dos` 或编辑器行尾设置）达到同样目的：只改目标行、保持文件原有行尾。
- **新建文件**：无需行尾核查（新文件行尾本就由你决定，跟随仓库主流即可）。
- **TDD 纪律**：每个含代码改动的 Task 先落失败测试并确认失败信息符合「Expected」，再写最小实现使其通过；最后该测试文件全绿、且步骤中列出的相关回归不退化，才 commit。
- **提交粒度**：一个 Task 一个 commit；message 沿用仓库风格（`fix(graph): …` / `feat(graph): …` / `docs: …`），并在结尾附 `Co-Authored-By` 行（看仓库最近 commit 的署名格式）。
- **改动面**：只改本 Task「Files」中列出的文件。若发现计划与实际代码有出入（函数签名变了、行号偏移、`old_string` 匹配不到等），**以「实现该 Step 的意图」为准做最小适配**，并在该 Task 末尾记一行说明；不要擅自重构无关代码、不要顺手「优化」计划外的东西。
- **外部引用**：计划中出现的「设计文档 §X」「Phase 4」等仅为出处标注，执行**不依赖**阅读它们——所需上下文已内联在各 Step 与下面的「背景」表中。
- **标注「需用户确认」/「由执行者直接运行」的 Task**：前者必须停下来向人类维护者提问后再继续；后者指该步含一次性临时脚本与人工观察，由执行你这个计划的主体亲自跑（不要再下分一层去跑然后丢弃证据），跑完按步骤删除临时脚本。

---

## 背景：本计划要解决的问题（评审已确认）

| 编号 | 问题 | 性质 | 证据 |
|---|---|---|---|
| #5 | 新图丢掉多轮历史：`history` 传进 state 但**无任何节点消费**，相对旧 `AgentLoop` 是单轮无记忆的功能回归 | 正确性回归 | `runner.py:57` 注入 history；`coordinator.py`/`knowledge.py`/`finalize.py` 均只读 `state["query"]` |
| #6 | 节点异常不兜底：coordinator/knowledge/finalize 未包 try/except，LLM 抛错直接炸 `astream`、SSE 流断在中途，违背设计文档 §6「不中断全图」 | 健壮性 | 仅 `knowledge_gap_node` 包了落库异常 |
| #8 | token 漏算：`runner` 只统计 `prompt_est + finalize 输出`，coordinator/knowledge_gap 的 LLM 调用未计入，前端 token 系统性低估；且 `chat.py:455` 把 `estimated` 写死为 True | 可观测/口径 | `runner.py:65-118`，`agent.py:454-455` |
| #7 | `trace` 是死数据：一路 `operator.add` 累积，但 `runner` 只从 values 取 citations，从不读 trace；`done` 帧 `steps` 写死 `[]`；设计文档 §7 规划的 `AgentTrace` 表从未建 | 可观测 | `runner.py:118`；`models/chat_history.py` 无 AgentTrace |
| #4 | 工程优化（结构化输出/分类缓存/投机检索）——**经评估后降级**，见 Phase 2 Task 5 | 优化 | `factory.py` 确认 chat_model 为 ChatTongyi/ChatOllama |
| #1+#2 | 缺反馈回路 + Coordinator 只能单选 task_type，本质是单向流水线而非协同 | 架构 | `build.py` 全是单向前进边；`coordinator.py:49-53` 单枚举输出 |

---

# Phase 1：确定性修复（#5 / #6 / #8）

> 三项都不动图结构与 SSE 契约，风险低、收益高，按 TDD 逐项落地。每项独立可合并。

## Task 1: #5 多轮历史注入（finalize + coordinator）

**目标：** 让 finalize 生成与 coordinator 路由都能看到对话历史，恢复多轮记忆。`history` 形如 `[(user, assistant), ...]`。

**Files:**
- Modify: `backend/app/agent/graph/nodes/finalize.py`
- Modify: `backend/app/agent/graph/nodes/coordinator.py`
- Test: `backend/tests/test_graph_finalize_node.py`（追加）
- Test: `backend/tests/test_graph_coordinator_node.py`（追加）

- [ ] **Step 1: 写失败测试（finalize 带 history）**

在 `backend/tests/test_graph_finalize_node.py` 末尾追加：
```python
@pytest.mark.asyncio
async def test_finalize_includes_history(monkeypatch):
    captured = {}

    class _Msg:
        def __init__(self, c): self.content = c

    async def _fake_ainvoke(messages):
        captured["messages"] = messages
        return _Msg("基于上下文的回答")

    import app.agent.graph.nodes.finalize as fz

    class _Fake:
        ainvoke = staticmethod(_fake_ainvoke)
    monkeypatch.setattr(fz, "chat_model", _Fake())

    state = {
        "query": "那它2025版改了什么",
        "documents": [],
        "history": [("2023版报销上限多少", "上限是500元")],
    }
    await finalize_node(state)
    roles = [m["role"] for m in captured["messages"]]
    # system + 历史(user,assistant) + 当前 user
    assert roles == ["system", "user", "assistant", "user"]
    assert captured["messages"][1]["content"] == "2023版报销上限多少"
    assert captured["messages"][2]["content"] == "上限是500元"
    assert "那它2025版改了什么" in captured["messages"][-1]["content"]
```

- [ ] **Step 2: 运行确认失败**

```bash
uv run pytest tests/test_graph_finalize_node.py::test_finalize_includes_history -v
```
Expected: FAIL —— 当前 `_build_messages` 不展开 history，`roles` 为 `["system", "user"]`。

- [ ] **Step 3: 改 finalize 的 `_build_messages`**

把 `backend/app/agent/graph/nodes/finalize.py` 的 `_build_messages` 整体替换为：
```python
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

    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
    for pair in state.get("history") or []:
        if isinstance(pair, (list, tuple)) and len(pair) == 2:
            u, a = pair
            messages.append({"role": "user", "content": u or ""})
            messages.append({"role": "assistant", "content": a or ""})
    messages.append({"role": "user", "content": user})
    return messages
```
> 注意：`task_messages` 路径（tool 构造的对比/报告/申请 messages）一期**不**注入 history——任务类多为单轮指令，且改 tool 接口会动 Phase 4 契约。该限制记在「已知限制」。

- [ ] **Step 4: 写失败测试（coordinator 用最近一轮做指代消解）**

在 `backend/tests/test_graph_coordinator_node.py` 末尾追加：
```python
@pytest.mark.asyncio
async def test_coordinator_uses_recent_history(monkeypatch):
    captured = {}

    class _Msg:
        def __init__(self, c): self.content = c

    async def _fake_ainvoke(messages):
        captured["messages"] = messages
        return _Msg('{"task_type":"knowledge_qa","need_retrieval":true,"reason":"x"}')

    import app.agent.graph.nodes.coordinator as co

    class _Fake:
        ainvoke = staticmethod(_fake_ainvoke)
    monkeypatch.setattr(co, "chat_model", _Fake())

    state = {
        "query": "那它呢",
        "history": [("差旅报销上限", "上限500元")],
    }
    await coordinator_node(state)
    user_content = captured["messages"][-1]["content"]
    assert "差旅报销上限" in user_content and "那它呢" in user_content
```
（确认文件顶部已 `from app.agent.graph.nodes.coordinator import coordinator_node`；若无则在导入区补上。）

- [ ] **Step 5: 运行确认失败**

```bash
uv run pytest tests/test_graph_coordinator_node.py::test_coordinator_uses_recent_history -v
```
Expected: FAIL —— 当前 coordinator 只把 `state["query"]` 放进 user 消息，不含历史。

- [ ] **Step 6: 改 coordinator 注入最近一轮上下文**

在 `backend/app/agent/graph/nodes/coordinator.py` 的 `coordinator_node` 内，把构造 `messages` 的两行：
```python
    messages = [
        {"role": "system", "content": _COORDINATOR_PROMPT},
        {"role": "user", "content": state["query"]},
    ]
```
替换为：
```python
    # 仅取最近一轮做指代消解（"那它呢"），避免长历史干扰分类的 JSON 输出
    context = ""
    history = state.get("history") or []
    if history and isinstance(history[-1], (list, tuple)) and len(history[-1]) == 2:
        last_u, last_a = history[-1]
        context = f"（上一轮——用户：{last_u}；助手：{last_a}）\n"
    messages = [
        {"role": "system", "content": _COORDINATOR_PROMPT},
        {"role": "user", "content": f"{context}当前问题：{state['query']}"},
    ]
```

- [ ] **Step 7: 运行两个测试文件确认通过 + 不退化**

```bash
uv run pytest tests/test_graph_finalize_node.py tests/test_graph_coordinator_node.py -v
```
Expected: 全部 PASS（含既有用例）。

- [ ] **Step 8: 行尾核查**

```bash
git diff --stat app/agent/graph/nodes/finalize.py app/agent/graph/nodes/coordinator.py
git diff --stat --ignore-all-space app/agent/graph/nodes/finalize.py app/agent/graph/nodes/coordinator.py
```
两者差距大则对该文件用 PowerShell 转回 CRLF：
```powershell
$f = "app/agent/graph/nodes/finalize.py"
$text = [System.Text.Encoding]::UTF8.GetString([System.IO.File]::ReadAllBytes($f))
$text = ($text -replace "`r`n", "`n") -replace "`n", "`r`n"
$utf8 = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($f, $text, $utf8)
```

- [ ] **Step 9: Commit**

```bash
git add app/agent/graph/nodes/finalize.py app/agent/graph/nodes/coordinator.py tests/test_graph_finalize_node.py tests/test_graph_coordinator_node.py
git commit -m "fix(graph): 恢复多轮历史——finalize 展开 history、coordinator 用最近一轮做指代消解"
```

---

## Task 2: #6 节点异常兜底（不中断全图）

**目标：** coordinator/knowledge/finalize 任一 LLM/检索调用抛异常时，节点**不向外抛**，而是降级返回 + 写 `trace` failed + 发 failed step，保证 `astream` 正常结束、SSE 必然收尾。并在 `runner` 末尾补「无 token 产出时用 `final_answer` 兜底发一帧」，让 finalize 异常的兜底文本可见。

**Files:**
- Modify: `backend/app/agent/graph/nodes/coordinator.py`
- Modify: `backend/app/agent/graph/nodes/knowledge.py`
- Modify: `backend/app/agent/graph/nodes/finalize.py`
- Modify: `backend/app/agent/graph/runner.py`
- Test: `backend/tests/test_graph_node_error_handling.py`（新建）

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_graph_node_error_handling.py`:
```python
import pytest

from app.agent.graph.nodes.coordinator import coordinator_node
from app.agent.graph.nodes.knowledge import knowledge_node
from app.agent.graph.nodes.finalize import finalize_node


@pytest.mark.asyncio
async def test_coordinator_falls_back_on_llm_error(monkeypatch):
    import app.agent.graph.nodes.coordinator as co

    async def _boom(_m):
        raise RuntimeError("LLM down")

    class _Fake:
        ainvoke = staticmethod(_boom)
    monkeypatch.setattr(co, "chat_model", _Fake())

    update = await coordinator_node({"query": "随便", "history": []})
    # 降级为保守 plan，不抛异常
    assert update["plan"]["need_retrieval"] is True
    assert update["trace"][0]["status"] == "failed"


@pytest.mark.asyncio
async def test_knowledge_degrades_on_retrieval_error(monkeypatch):
    import app.agent.graph.nodes.knowledge as kn

    async def _boom(query, filter_meta=None):
        raise RuntimeError("vector store down")
    monkeypatch.setattr(kn.rag_service, "get_documents_for_agent", _boom)

    update = await knowledge_node({"query": "x", "identity": None})
    assert update["documents"] == []
    assert update["is_enough"] is False
    assert update["trace"][0]["status"] == "failed"


@pytest.mark.asyncio
async def test_finalize_returns_fallback_text_on_llm_error(monkeypatch):
    import app.agent.graph.nodes.finalize as fz

    async def _boom(_m):
        raise RuntimeError("LLM down")

    class _Fake:
        ainvoke = staticmethod(_boom)
    monkeypatch.setattr(fz, "chat_model", _Fake())

    update = await finalize_node({"query": "x", "documents": [], "history": []})
    assert update["final_answer"]            # 非空兜底文本
    assert update["trace"][0]["status"] == "failed"
```

- [ ] **Step 2: 运行确认失败**

```bash
uv run pytest tests/test_graph_node_error_handling.py -v
```
Expected: 三个用例都因异常向外抛而 FAIL（ERROR）。

- [ ] **Step 3: coordinator 兜底**

`backend/app/agent/graph/nodes/coordinator.py` 的 `coordinator_node`，把
```python
    msg = await chat_model.ainvoke(messages)
    text = msg.content if hasattr(msg, "content") else str(msg)
    plan = _parse_plan(text)
```
替换为：
```python
    try:
        msg = await chat_model.ainvoke(messages)
        text = msg.content if hasattr(msg, "content") else str(msg)
        plan = _parse_plan(text)
        plan_status = "done"
    except Exception as e:
        from app.core.logger_handler import logger
        logger.error(f"[Coordinator] 分类失败，降级走检索: {e}", exc_info=True)
        plan = dict(_FALLBACK_PLAN)
        plan_status = "failed"
```
并把结尾 `return` 的 trace 行改为带状态：
```python
    return {
        "plan": plan,
        "trace": [{"agent": "coordinator", "status": plan_status,
                   "output": json.dumps(plan, ensure_ascii=False)}],
    }
```

- [ ] **Step 4: knowledge 兜底**

`backend/app/agent/graph/nodes/knowledge.py` 的 `knowledge_node`，把
```python
    identity = state.get("identity")
    filter_meta = await _build_filter(identity)
    result = await rag_service.get_documents_for_agent(state["query"], filter_meta=filter_meta)

    documents = result.get("documents", [])
    citations = result.get("citations", [])
    is_enough = result.get("is_enough", bool(documents))
    max_score = result.get("max_score")
```
替换为：
```python
    identity = state.get("identity")
    node_status = "done"
    try:
        filter_meta = await _build_filter(identity)
        result = await rag_service.get_documents_for_agent(state["query"], filter_meta=filter_meta)
        documents = result.get("documents", [])
        citations = result.get("citations", [])
        is_enough = result.get("is_enough", bool(documents))
        max_score = result.get("max_score")
    except Exception as e:
        from app.core.logger_handler import logger
        logger.error(f"[Knowledge] 检索失败，降级为空依据: {e}", exc_info=True)
        documents, citations, is_enough, max_score = [], [], False, None
        node_status = "failed"
```
并把 trace 行的 `"status": "done"` 改为 `"status": node_status`。

- [ ] **Step 5: finalize 兜底**

`backend/app/agent/graph/nodes/finalize.py` 的 `finalize_node`，把
```python
    messages = state.get("task_messages") or _build_messages(state)
    msg = await chat_model.ainvoke(messages)
    answer = msg.content if hasattr(msg, "content") else str(msg)

    return {
        "final_answer": answer,
        "trace": [{"agent": "finalize", "status": "done", "output": answer[:200]}],
    }
```
替换为：
```python
    messages = state.get("task_messages") or _build_messages(state)
    try:
        msg = await chat_model.ainvoke(messages)
        answer = msg.content if hasattr(msg, "content") else str(msg)
        status = "done"
    except Exception as e:
        from app.core.logger_handler import logger
        logger.error(f"[Finalize] 生成失败，输出兜底文本: {e}", exc_info=True)
        answer = "抱歉，生成回答时服务出现异常，请稍后重试。"
        status = "failed"

    return {
        "final_answer": answer,
        "trace": [{"agent": "finalize", "status": status, "output": answer[:200]}],
    }
```
> 说明：finalize 正常时 token 走 `messages` 模式自动流出；异常时 `ainvoke` 不会产 token，靠下一步 runner 兜底把 `final_answer` 补成一帧 token。

- [ ] **Step 6: runner 末尾「无 token 兜底」**

在 `backend/app/agent/graph/runner.py` 中：
1) 让 `values` 模式也捕获 `final_answer`。把
```python
            if mode == "values":
                if isinstance(payload, dict) and payload.get("citations") is not None:
                    final_citations = payload["citations"]
                continue
```
改为（在循环外先初始化 `final_answer_state = ""`）：
```python
            if mode == "values":
                if isinstance(payload, dict):
                    if payload.get("citations") is not None:
                        final_citations = payload["citations"]
                    if payload.get("final_answer"):
                        final_answer_state = payload["final_answer"]
                continue
```
2) 在 `async for` 循环**之前**加 `final_answer_state = ""`。
3) 在循环结束、发 `agent_step_update` 之前插入兜底：
```python
        # 兜底：若全程没有任何 token 流出（如 finalize 异常或 provider 没流 token），
        # 用最终 state 的 final_answer 补一帧，保证用户能看到内容。
        if not full_answer and final_answer_state:
            yield {"type": "token", "data": final_answer_state}
            content_buf = final_answer_state
```

- [ ] **Step 7: 运行确认通过**

```bash
uv run pytest tests/test_graph_node_error_handling.py -v
```
Expected: 3 个用例全 PASS。

- [ ] **Step 8: 行尾核查（四个文件）**

```bash
git diff --stat app/agent/graph/nodes/coordinator.py app/agent/graph/nodes/knowledge.py app/agent/graph/nodes/finalize.py app/agent/graph/runner.py
git diff --stat --ignore-all-space app/agent/graph/nodes/coordinator.py app/agent/graph/nodes/knowledge.py app/agent/graph/nodes/finalize.py app/agent/graph/runner.py
```
差距大的文件用 Task 1 Step 8 的 PowerShell 片段逐个转回 CRLF。

- [ ] **Step 9: Commit**

```bash
git add app/agent/graph/nodes/coordinator.py app/agent/graph/nodes/knowledge.py app/agent/graph/nodes/finalize.py app/agent/graph/runner.py tests/test_graph_node_error_handling.py
git commit -m "fix(graph): 节点异常兜底——降级不中断全图，runner 用 final_answer 兜底收尾"
```

---

## Task 3: #8 token 全量计费

**目标：** 把 coordinator / knowledge_gap / finalize 三处 LLM 调用的真实 token 全部计入。state 增 `token_usage`（`operator.add` reducer），各节点累加本次调用 total（provider 给则用精确值，否则估算兜底）；runner 的 `done` 帧用累计值。顺手修 `chat.py` 把 `estimated` 写死的 bug。

**Files:**
- Modify: `backend/app/agent/token_utils.py`（新增 `extract_total_tokens`）
- Modify: `backend/app/agent/graph/state.py`（新增 `token_usage` 字段）
- Modify: `backend/app/agent/graph/nodes/coordinator.py`
- Modify: `backend/app/agent/graph/nodes/knowledge_gap.py`
- Modify: `backend/app/agent/graph/nodes/finalize.py`
- Modify: `backend/app/agent/graph/runner.py`
- Modify: `backend/app/agent/agent.py`（修 estimated 写死）
- Test: `backend/tests/test_token_accounting.py`（新建）

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_token_accounting.py`:
```python
from app.agent.token_utils import extract_total_tokens


class _MsgUsageMeta:
    usage_metadata = {"total_tokens": 123}


class _MsgRespMeta:
    response_metadata = {"token_usage": {"total_tokens": 77}}


class _MsgNone:
    content = "x"


def test_extract_from_usage_metadata():
    assert extract_total_tokens(_MsgUsageMeta()) == 123


def test_extract_from_response_metadata():
    assert extract_total_tokens(_MsgRespMeta()) == 77


def test_extract_returns_none_when_absent():
    assert extract_total_tokens(_MsgNone()) is None
    assert extract_total_tokens(None) is None
```

- [ ] **Step 2: 运行确认失败**

```bash
uv run pytest tests/test_token_accounting.py -v
```
Expected: FAIL —— `ImportError: cannot import name 'extract_total_tokens'`。

- [ ] **Step 3: 在 token_utils 实现 `extract_total_tokens`**

在 `backend/app/agent/token_utils.py` 末尾追加（逻辑等同 `runner._chunk_total_tokens`，提取为公共函数供节点复用）：
```python
def extract_total_tokens(message):
    """从 LangChain message/chunk 上抠 total_tokens；拿不到返回 None（由调用方估算兜底）。"""
    if message is None:
        return None
    usage = getattr(message, "usage_metadata", None)
    if isinstance(usage, dict):
        total = usage.get("total_tokens")
        if total:
            return int(total)
    rmeta = getattr(message, "response_metadata", None)
    if isinstance(rmeta, dict):
        token_usage = rmeta.get("token_usage") or rmeta.get("usage")
        if isinstance(token_usage, dict):
            total = token_usage.get("total_tokens")
            if total:
                return int(total)
    return None
```

- [ ] **Step 4: 运行确认 token_utils 测试通过**

```bash
uv run pytest tests/test_token_accounting.py -v
```
Expected: 3 个用例 PASS。

- [ ] **Step 5: state 增 `token_usage` 字段**

在 `backend/app/agent/graph/state.py` 的 `trace` 字段上方插入：
```python
    # token 计量（各节点 append 本次 LLM 调用的 total，reducer 累加）
    token_usage: Annotated[int, operator.add]
```
（`Annotated`/`operator` 已在文件顶部导入，无需改 import。）

- [ ] **Step 6: 三个节点累加 token_usage**

- `coordinator.py`：Task 2 Step 3 改造后的 try 块里，`plan_status = "done"` 之后加：
```python
        from app.agent.token_utils import extract_total_tokens, estimate_messages_tokens
        coord_tokens = extract_total_tokens(msg) or estimate_messages_tokens(messages) + estimate_messages_tokens([{"content": text}])
```
并在 `return` 字典里加一项 `"token_usage": coord_tokens`。except 分支里 `coord_tokens = 0`、同样返回 `"token_usage": 0`（保持 key 存在）。

- `knowledge_gap.py`：在 `gap = _parse_gap(...)` 之后加：
```python
    from app.agent.token_utils import extract_total_tokens, estimate_messages_tokens
    gap_tokens = extract_total_tokens(msg) or estimate_text_tokens(text)  # text 已是 LLM 输出
```
（需在文件顶部 `from app.agent.token_utils import estimate_text_tokens`。）并在 return 字典加 `"token_usage": gap_tokens`。

- `finalize.py`：Task 2 Step 5 改造后的 try 块里，`status = "done"` 之后加：
```python
        from app.agent.token_utils import extract_total_tokens
        fin_tokens = extract_total_tokens(msg) or 0   # 0 表示由 runner 的流式估算口径兜底
```
except 分支 `fin_tokens = 0`。return 字典加 `"token_usage": fin_tokens`。

> 口径说明：provider（ChatTongyi）的 `total_tokens` 含 prompt+completion，各次调用相加即真实 API 消耗。拿不到精确值时用估算兜底，避免出现 0。

- [ ] **Step 7: runner 用累计 token 作为 done 值**

在 `backend/app/agent/graph/runner.py`：
1) `values` 模式分支里追加捕获（与 Task 2 Step 6 的 `final_answer_state` 并列）：
```python
                    if payload.get("token_usage") is not None:
                        graph_token_usage = payload["token_usage"]
```
2) 循环前初始化 `graph_token_usage = 0`。
3) 把 `done` 帧的 `final_tokens` 计算改为：
```python
        # 优先用图内累计的精确 token；为 0 时回落到 prompt+finalize 输出的估算
        estimated_total = prompt_est + estimate_text_tokens(content_buf)
        final_tokens = graph_token_usage if graph_token_usage else (
            accurate_tokens if accurate_tokens is not None else estimated_total
        )
```

- [ ] **Step 8: 修 chat.py 的 estimated 写死 bug**

在 `backend/app/agent/agent.py` 的 `get_agent_stream_response`，把 usage 分支
```python
        elif event["type"] == "usage":
            yield f"data: {json.dumps({'type': 'usage', 'tokens': event['tokens'], 'estimated': True}, ensure_ascii=False)}\n\n"
```
改为如实透传事件里的 `estimated`：
```python
        elif event["type"] == "usage":
            yield f"data: {json.dumps({'type': 'usage', 'tokens': event['tokens'], 'estimated': event.get('estimated', True)}, ensure_ascii=False)}\n\n"
```

- [ ] **Step 9: 全量回归（确认 token 改动不破坏既有流式/契约）**

```bash
uv run pytest tests/test_graph_runner_sse.py tests/test_agent_sse_steps.py tests/test_token_accounting.py -v
```
Expected: 全部 PASS。

- [ ] **Step 10: 行尾核查 + Commit**

```bash
git diff --stat app/agent/token_utils.py app/agent/graph/state.py app/agent/graph/nodes/coordinator.py app/agent/graph/nodes/knowledge_gap.py app/agent/graph/nodes/finalize.py app/agent/graph/runner.py app/agent/agent.py
git diff --stat --ignore-all-space <同上文件列表>
```
差距大的逐个 PowerShell 转回 CRLF。然后：
```bash
git add app/agent/token_utils.py app/agent/graph/state.py app/agent/graph/nodes/coordinator.py app/agent/graph/nodes/knowledge_gap.py app/agent/graph/nodes/finalize.py app/agent/graph/runner.py app/agent/agent.py tests/test_token_accounting.py
git commit -m "fix(graph): token 全量计费——各节点累加真实 usage，修 usage estimated 写死"
```

---

## Task 4: Phase 1 端到端验证（由执行者直接运行）

**Files:** 无（验证任务）

- [ ] **Step 1: 全量回归**

```bash
uv run pytest tests/ -q
```
Expected: 全绿。失败原样贴报告，判断是否本次引入。

- [ ] **Step 2: 真实多轮 + 异常 + token 验证（临时脚本，验证后删除）**

Create `backend/_tmp_phase1_verify.py`:
```python
import asyncio
from app.agent.graph.runner import graph_runner


async def run(q, history):
    events = []
    async for e in graph_runner.stream(q, history=history, identity=None):
        events.append(e)
    tokens = "".join(e["data"] for e in events if e["type"] == "token")
    usage = [e for e in events if e["type"] == "usage"]
    done = [e for e in events if e["type"] == "done"]
    print(f"\nQ={q!r}")
    print(" 回答前120字:", tokens[:120])
    print(" done tokens:", done[-1]["tokens"] if done else None)


async def main():
    # 多轮指代：第二问依赖第一轮上下文
    await run("那它2025版改了什么", [("2023版差旅报销上限多少", "上限是500元")])


if __name__ == "__main__":
    asyncio.run(main())
```
运行：`PYTHONPATH=<backend绝对路径> uv run python _tmp_phase1_verify.py`
预期：回答能体现「2025版」与上一轮「差旅报销」的关联（指代消解生效）；`done tokens` 明显大于仅 finalize 输出的估算（含 coordinator 计费）。验证后删除脚本。

- [ ] **Step 3: 记录结论**

在本任务下方记录 `Phase 1 通过 / 问题`。通过即可 ff-merge 到 master（按全局 worktree 流程）。

---

# Phase 2：工程加固

## Task 5: #7 AgentTrace 落库 + done 帧带 trace 摘要

**目标：** 把一路累积却被丢弃的 `trace` 用起来——建 `agent_traces` 表，runner 末尾把整条 trace 落库（事后复盘），并把 `done` 帧写死的 `steps: []` 替换为 trace 摘要。需给 `graph_runner.stream` 透传 `session_id`。

**Files:**
- Modify: `backend/app/models/chat_history.py`（新增 `AgentTrace` model）
- Create: `backend/app/services/agent_trace_service.py`
- Modify: `backend/app/agent/graph/runner.py`（接收 session_id + 落库 + done 带 trace）
- Modify: `backend/app/agent/agent.py`（调用处传 session_id）
- Test: `backend/tests/test_agent_trace_service.py`（新建）

- [ ] **Step 1: 写失败测试（service 落库/查询）**

Create `backend/tests/test_agent_trace_service.py`:
```python
import pytest

from app.services.agent_trace_service import agent_trace_service


@pytest.mark.asyncio
async def test_save_and_list_traces():
    sid = "test-session-trace-1"
    trace = [
        {"agent": "coordinator", "status": "done", "output": "{...}"},
        {"agent": "knowledge", "status": "done", "output": "documents=2"},
        {"agent": "finalize", "status": "done", "output": "答案..."},
    ]
    await agent_trace_service.save_traces(session_id=sid, trace=trace)
    rows = await agent_trace_service.list_by_session(sid)
    assert [r["agent_name"] for r in rows] == ["coordinator", "knowledge", "finalize"]
    assert rows[1]["status"] == "done"
```
> 该测试需要可用 DB（与既有 `test_knowledge_gap_service.py` 同等前提）；若 CI 无 DB，标记 `@pytest.mark.integration` 并随既有缺口 service 测试一同跳过/运行。

- [ ] **Step 2: 运行确认失败**

```bash
uv run pytest tests/test_agent_trace_service.py -v
```
Expected: FAIL —— `ModuleNotFoundError: app.services.agent_trace_service`。

- [ ] **Step 3: 新增 AgentTrace model**

在 `backend/app/models/chat_history.py` 末尾追加（紧跟 `KnowledgeGap` 之后，风格一致）：
```python
class AgentTrace(Base):
    """多 agent 协同轨迹：每个节点一行，供事后复盘。实时展示仍走 SSE，不依赖查库。"""
    __tablename__ = "agent_traces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), index=True, nullable=False)
    agent_name = Column(String(64), nullable=False)
    output = Column(Text, default="")
    status = Column(String(20), nullable=False, default="done")  # done/failed/skipped
    seq = Column(Integer, default=0)   # 同 session 内顺序
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```
（`Column/Integer/String/Text/DateTime/func` 均已在文件顶部导入。`create_all` 会自动建表。）

- [ ] **Step 4: 新增 agent_trace_service**

Create `backend/app/services/agent_trace_service.py`:
```python
"""Agent 协同轨迹 service：批量落库 / 按 session 查询。仿 knowledge_gap_service。"""
from typing import List, Dict, Any

from app.db.db_config import AsyncSessionLocal
from app.models.chat_history import AgentTrace
from app.core.logger_handler import logger


class AgentTraceService:

    async def save_traces(self, session_id: str, trace: List[Dict[str, Any]]) -> None:
        """把一次图执行的 trace 批量落库；失败只记日志，不影响主流程。"""
        if not session_id or not trace:
            return
        try:
            async with AsyncSessionLocal() as db:
                for i, item in enumerate(trace):
                    db.add(AgentTrace(
                        session_id=session_id,
                        agent_name=str(item.get("agent", "unknown")),
                        output=str(item.get("output", ""))[:4000],
                        status=str(item.get("status", "done")),
                        seq=i,
                    ))
                await db.commit()
        except Exception as e:
            logger.error(f"[AgentTrace] 落库失败 session={session_id}: {e}", exc_info=True)

    async def list_by_session(self, session_id: str) -> List[Dict[str, Any]]:
        async with AsyncSessionLocal() as db:
            rows = await db.run_sync(
                lambda s: s.query(AgentTrace)
                .filter(AgentTrace.session_id == session_id)
                .order_by(AgentTrace.seq.asc())
                .all()
            )
            return [{
                "agent_name": r.agent_name, "status": r.status,
                "output": r.output, "seq": r.seq,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            } for r in rows]


agent_trace_service = AgentTraceService()
```

- [ ] **Step 5: 运行确认 service 测试通过**

```bash
uv run pytest tests/test_agent_trace_service.py -v
```
Expected: PASS（DB 可用前提下）。

- [ ] **Step 6: runner 接 session_id + 落库 + done 带 trace**

在 `backend/app/agent/graph/runner.py`：
1) `stream` 签名加 `session_id: Optional[str] = None`。
2) `values` 模式分支追加捕获 trace（与前面并列）：
```python
                    if payload.get("trace") is not None:
                        final_trace = payload["trace"]
```
循环前初始化 `final_trace = []`。
3) 发 `done` 之前落库 + 用 trace 摘要替换空 steps：
```python
        if session_id and final_trace:
            from app.services.agent_trace_service import agent_trace_service
            await agent_trace_service.save_traces(session_id, final_trace)
        trace_steps = [
            {"agent": t.get("agent"), "status": t.get("status")}
            for t in final_trace
        ]
```
4) `done` 帧把 `"steps": []` 改为 `"steps": trace_steps`。

- [ ] **Step 7: agent.py 调用处传 session_id**

在 `backend/app/agent/agent.py` 把
```python
        event_source = graph_runner.stream(query, history, identity=identity)
```
改为
```python
        event_source = graph_runner.stream(query, history, identity=identity, session_id=session_id)
```

- [ ] **Step 8: 行尾核查 + 全量回归 + Commit**

```bash
uv run pytest tests/ -q
git diff --stat app/models/chat_history.py app/agent/graph/runner.py app/agent/agent.py
git diff --stat --ignore-all-space app/models/chat_history.py app/agent/graph/runner.py app/agent/agent.py
```
差距大的转回 CRLF。然后：
```bash
git add app/models/chat_history.py app/services/agent_trace_service.py app/agent/graph/runner.py app/agent/agent.py tests/test_agent_trace_service.py
git commit -m "feat(graph): AgentTrace 落库 + done 帧带 trace 摘要（trace 不再是死数据）"
```

---

## Task 6: #4 工程优化 —— 评估与决策（不强行实施，需用户确认）

**这是一个决策任务，不是实施任务。** 经核实代码后，原 #4 的三个子项都需重新权衡：

- **结构化输出（`with_structured_output`）**：`chat_model` 是 `ChatTongyi`（`factory.py:97`），langchain-community 对它的 structured-output 支持不稳定，强上风险高于收益。现有 coordinator/knowledge_gap 的「正则抠 JSON + `_FALLBACK_PLAN`/`_fallback_gap` 兜底」已相当健壮（Task 2 又加了异常兜底）。**决策：不做**，除非后续切换到原生支持 function-calling 的 provider。
- **分类结果 Redis 缓存**：Phase 1 Task 1 给 coordinator 注入了 history 做指代消解后，分类已**依赖上下文**，缓存键必须含 history，命中率极低。缓存与 #5 直接冲突。**决策：不做**。
- **投机检索（coordinator 与首次检索并行）降延迟**：这需要改图结构（并行节点 + fan-in），本质属于 Phase 3 的图编排改造范畴。**决策：并入 Phase 3 一起设计**，不在 Phase 2 单独做。

- [ ] **Step 1: 确认上述决策**

与维护者确认「#4 不单独实施，投机检索并入 Phase 3」。若维护者坚持要分类缓存，则需重新设计缓存键（含归一化 history hash）并接受低命中率——另起独立计划。

- [ ] **Step 2: 记录结论**

在本任务下方写明 #4 的最终处置，关闭该项。

---

# Phase 3：架构升级（#1 Critic 回路 + #2 Coordinator 规划器）

> ⚠️ **这是开放设计，不是可直接执行的 TDD。** 实现前**必须先做一轮需求/方案探索（brainstorming）** 把形态定下来，再产出一份独立的、像本计划一样自包含的实施计划。本节只锁定方向与决策点，避免现在写出注定要返工的假精确步骤。**任意执行者读到 Phase 3 都应停下，不要照着「候选形态」直接写代码。**

## #1 Critic / 反馈回路 —— 把单向流水线升级为「可打回重做」

**要解决的：** 设计文档 §2 承诺的 `Knowledge → Coordinator → Task → Coordinator → Finalize` 回边至今不存在（`build.py` 全是单向边）。

**候选形态（设计阶段定夺）：**
1. **新增 `critic` 节点**：在 finalize 草稿后（或 knowledge 证据后）做质量评估，不满意则条件边回退到 knowledge/task 重做。
2. **复用 coordinator 作为汇合点**：knowledge/task 完成后回到 coordinator，由它判断「够了吗/ 再来一轮吗」。

**必须解决的决策点：**
- **防死循环**：state 加 `revision_count` + 上限（如 ≤2），LangGraph `recursion_limit` 兜底。
- **流式契约**：critic/重做轮的 LLM token **绝不能**流给用户（`stream_bridge` 只放行 `finalize` 节点 token，重做时要保证最终只流最后一遍 finalize）。这是最大风险点，需 spike 验证。
- **评估标准**：critic 用什么判据（覆盖度/是否答非所问/置信度），是否再花一次 LLM 调用（成本）。
- **token 计费**：重做轮的多次调用要计入 Phase 1 Task 3 的 `token_usage`（已是 `operator.add`，天然支持）。

## #2 Coordinator 从「单选分类」升级为「规划器」

**要解决的：** `coordinator.py` 一次只产出一个 `task_type`，无法表达「先对比新旧制度**再**生成变更报告」这类复合任务。

**候选形态（设计阶段定夺）：**
- Coordinator 输出**任务列表/DAG**（`plan.steps = [{task_type, depends_on}, ...]`）而非单枚举。
- 配合 LangGraph `Send` API 做 fan-out/fan-in，支持多文档对比这类天然并行场景（`trace` 的 `operator.add` reducer 已为并行铺好路）。

**必须解决的决策点：**
- `AgentState` 如何承载多步结果（`task_results: Annotated[list, operator.add]`）。
- 与 #1 回路如何共存（规划器 + 重做轮的交互复杂度）。
- 是否真有复合任务需求驱动——**避免 YAGNI**，先确认业务场景再投入。

## Phase 3 启动条件

- Phase 1 + Phase 2 已合并且线上稳定。
- 已就「是否真需要复合任务 / 重做回路」与业务方确认（避免过度设计）。
- 满足条件后：先做需求/方案探索 → 再产出独立的自包含实施计划 → 才动代码。

---

## 已知限制（本计划范围内不处理，记录备查）

1. **task_messages 路径不带 history**（Phase 1 Task 1）：对比/报告/申请类任务在多轮场景下看不到上文。任务类多为单轮指令，影响小；如需支持需改 Phase 4 的 tool 接口。
2. **RAG 检索 query 不做指代消解改写**：Phase 1 只让生成/路由看到 history，检索仍用原始 query。「那它呢」这类问题的**检索**召回可能不准——属于独立增强项（history-aware query rewriting），未来可单列。
3. **trace 仅落库不暴露查询 API/前端页**：本计划只落库供事后复盘，未做查询接口（可仿 knowledge-gaps 的 API + 前端页后续补）。

---

## 计划自检

- **覆盖**：#5（Task 1）、#6（Task 2）、#8（Task 3）、Phase1 验证（Task 4）、#7（Task 5）、#4（Task 6 决策）、#1+#2（Phase 3 设计）——全部纳入项均有归属。
- **类型一致**：`token_usage`（state 字段 / 节点 return key / runner 读取 `graph_token_usage`）、`extract_total_tokens`（token_utils 定义 / 三节点调用）、`save_traces`/`list_by_session`（service 定义 / 测试调用 / runner 调用）命名前后一致。
- **无占位符**：Phase 1/2 每个改动步骤均给出可直接套用的真实代码与确切命令；Phase 3 明确标注为「需先做需求/方案探索的设计阶段」，非占位符。
