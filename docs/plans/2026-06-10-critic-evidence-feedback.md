# Critic 证据级反馈回路 + history-aware query 改写 实施计划

> **执行者须知（适用于任意能读写文件、运行命令的 AI 编码 agent —— Claude Code / Codex / Cursor 等均可）：** 本计划自包含，不依赖任何特定工具的私有能力或对话上下文。每个 Task 都给出确切文件路径、可直接套用的测试与实现代码、确切命令与预期输出。**按 Task 编号顺序逐个执行**；每个含代码改动的 Task 内部严格走 TDD：先写失败测试 → 运行确认失败 → 写实现 → 运行确认通过 → 行尾核查 → commit。除非某 Task 显式标注「需用户确认」，否则连续执行、无需中途征求确认。Steps 用 `- [ ]` 复选框便于逐项勾选跟踪。先通读下面的「执行约定」与「背景」两节再开始。

**Goal:** 在 `knowledge` 之后插入一个**证据级 critic 节点**，把现有单向流水线升级为「检索质量差时可改写 query 重检索一次」的反馈回路：对 `is_enough=False` 的检索结果判定「阈值过严可直接答 / query 写法问题需改写救援 / 真超范围记缺口」三档，并把 history-aware query 改写收进 critic 同一次 LLM 调用里。

**Architecture:** 不改对外 SSE 契约、不改 finalize 一次成型流式输出、不启用 checkpointer。新增 `critic_evidence` 节点用 DeepSeek flash（与 coordinator/knowledge_gap 同档）做结构化判定；`knowledge` 检测到 `reformulated_query` 时用它重检索；`max_revisions=1` 防死循环；critic 由 `AGENT_CRITIC_ENABLE` 总开关控制，关闭即退化回现行单向图。critic/重检索的 LLM token 由现行 `stream_bridge`「仅放行 finalize 节点 token」规则天然过滤，不泄漏给用户。

**Tech Stack:** Python 3.12, LangGraph（`StateGraph` 条件边 + 多 `stream_mode` astream）, langchain-core（`with_structured_output(include_raw=True)`）, pydantic `BaseModel`, ChatDeepSeek/ChatTongyi/ChatOllama（按 `LLM_TYPE` 切换）, pytest + pytest-asyncio。

**所有命令在 `backend/` 目录下用 `uv run` 执行。** 修改既有文件后必做行尾核查（`git diff --stat` vs `--ignore-all-space`，差距大则用 PowerShell 转回 CRLF，见每个 Task 的核查步骤）。新建文件无需核查。

**前置（已在 master，本计划直接依赖，无需重做）：**
- 多 agent 图骨架：`app/agent/graph/` 下 `state.py`/`build.py`/`runner.py`/`stream_bridge.py`/`_stream.py` + `nodes/`（coordinator/knowledge/task/knowledge_gap/finalize）已实现并跑通。
- 加固计划 [2026-06-09-multi-agent-hardening.md](./2026-06-09-multi-agent-hardening.md) 的 Phase 1/2 **已合并**：节点异常已包 try/except 兜底、`token_usage: Annotated[int, operator.add]` 已在 state、各节点已累加真实 token、`coordinator`/`knowledge_gap` 已用 `with_structured_output(include_raw=True)`、`AgentTrace` 已落库、`done` 帧已带 trace 摘要、`get_chat_model(role)` 分角色模型已就位。
- 设计文档：[docs/design/2026-06-10-critic-evidence-feedback-design.md](../design/2026-06-10-critic-evidence-feedback-design.md)（本计划是它的可执行落地版；§ 引用仅为出处标注，执行不依赖阅读）。

---

## 执行约定（环境与纪律，任意执行者先读）

- **仓库根**：本计划路径相对仓库根为 `docs/plans/2026-06-10-critic-evidence-feedback.md`；后端代码在 `backend/`，本计划只动 `backend/`。
- **工作目录**：除非某步另有说明，所有命令均在 `backend/` 目录下执行。
- **运行器**：统一用 `uv run <cmd>`（如 `uv run pytest ...`）。若环境无 `uv`，等价改用项目虚拟环境的 `python -m pytest`。`pyproject.toml` 里 `venv.path` 触发的 warning 无害，忽略。
- **平台**：开发机为 Windows + PowerShell，行尾核查步骤中的 PowerShell 片段按此假设。**核心约束是「修改既有文件时不要把整个文件的行尾从 CRLF 翻成 LF」**——很多编辑器/工具会在写入时统一成 LF，导致 `git diff` 把整文件每行都算作改动。非 Windows 平台用等效手段（`dos2unix`/`unix2dos` 或编辑器行尾设置）：只改目标行、保持文件原有行尾。
- **新建文件**：无需行尾核查（行尾跟随仓库主流即可）。
- **TDD 纪律**：每个含代码改动的 Task 先落失败测试并确认失败信息符合「Expected」，再写最小实现使其通过；最后该测试文件全绿、且步骤中列出的相关回归不退化，才 commit。
- **提交粒度**：一个 Task 一个 commit；message 沿用仓库风格（`feat(graph): …` / `fix(graph): …` / `refactor(graph): …` / `test(graph): …`），结尾附 `Co-Authored-By: Claude <noreply@anthropic.com>`。
- **改动面**：只改本 Task「Files」中列出的文件。若发现计划与实际代码有出入（函数签名变了、行号偏移、`old_string` 匹配不到等），**以「实现该 Step 的意图」为准做最小适配**，并在该 Task 末尾记一行说明；不要擅自重构无关代码。
- **标注「由执行者直接运行」的 Task**：指该步含一次性临时脚本与人工观察，由执行你这个计划的主体亲自跑，跑完按步骤删除临时脚本。

---

## 背景：本计划要解决的问题（设计已确认）

| 主题 | 现状 | 目标 |
|---|---|---|
| 单向流水线 | `build.py` 全是单向前进边，检索质量差（query 写法/指代未消解）→ 错就错到底，`is_enough=False` 直接进 `knowledge_gap`，**错失「改写 query 后能召回」的救援场景** | `knowledge` 后插 critic，`is_enough=False` 一律先评估；可改写救援则重检索一次 |
| 检索 query 不消解 | coordinator/finalize 已能看到 history（Phase 1 注入），但**检索 query 仍是原始字符串**，「那它 2025 版改了什么」丢给 RAG 召回不准 | 把 history-aware 改写收进 critic（同一次 LLM 调用顺手输出 `reformulated_query`），knowledge 重检索时优先用 |
| 流式契约风险 | finalize 一次成型流式输出是不变量；新增节点的 LLM token 绝不能流给用户 | critic 走 `with_structured_output().ainvoke()` 返回完整对象，**不经 messages 流**；`stream_bridge` 仅放行 `finalize` 节点 token，天然不泄漏。**零改动** |
| 成本与死循环 | 重做轮会多花 LLM 调用 | `is_enough=True` 高置信跳过 critic；`max_revisions=1`（改写最多一次）；`AGENT_CRITIC_ENABLE=false` 紧急回退 |

**修正后的路由（设计 §3）：**

```
START → coordinator ─(need_retrieval=false)─→ finalize
              └─(true)→ knowledge ─┬─ is_enough=true ──→ task/finalize
                                   └─ is_enough=false ─→ critic_evidence
                                          ├─ relevant ───────────────→ task/finalize
                                          ├─ needs_rewrite & 未超上限 → knowledge（带 reformulated_query）→ critic_evidence（再判）
                                          ├─ needs_rewrite & 已达上限 → knowledge_gap
                                          └─ out_of_scope ───────────→ knowledge_gap
```

最坏路径 `coordinator→knowledge→critic→knowledge→critic→knowledge_gap→finalize` 仅 7 步，远低于 LangGraph `recursion_limit` 默认 25。

**关键决策（设计 §15）：** 触发 = 仅 `is_enough=False` 走 critic；模型 = DeepSeek flash；重做上限 = 1；流式影响 = 零改动；范围 = critic + history-aware 改写共用一次 LLM 调用；删掉「低分直接 gap」快速通道，统一交给 critic。

---

## Task 1: 基础设施 —— AgentState 新字段 + factory critic 角色

**目标：** 先把 critic 回路需要的 state 字段和模型角色映射加上（纯加法，不改任何行为），为后续节点/路由打底。

**Files:**
- Modify: `backend/app/agent/graph/state.py`
- Modify: `backend/app/utils/factory.py`
- Test: `backend/tests/test_model_factory_roles.py`（追加 critic 断言）

- [ ] **Step 1: 写失败测试（critic 角色映射到 flash）**

在 `backend/tests/test_model_factory_roles.py` 的 `test_deepseek_role_mapping_uses_flash_and_pro` 里，`finalize` 断言之后追加一行：
```python
        assert factory.get_chat_model("finalize").model_name == "deepseek-v4-pro"
        # critic 证据评估：与 coordinator 同档（flash）
        assert factory.get_chat_model("critic").model_name == "deepseek-v4-flash"
```

- [ ] **Step 2: 运行确认失败**

```bash
uv run pytest tests/test_model_factory_roles.py::test_deepseek_role_mapping_uses_flash_and_pro -v
```
Expected: FAIL —— `critic` 不在 `_DEEPSEEK_ROLE_ENV`，`get_chat_model("critic")` 回退到 `finalize`，`model_name` 为 `deepseek-v4-pro` 而非 flash。

- [ ] **Step 3: factory 增加 critic 角色**

在 `backend/app/utils/factory.py` 的 `_DEEPSEEK_ROLE_ENV` 字典里，`"knowledge_gap"` 行之后插入：
```python
    "knowledge_gap": ("DEEPSEEK_MODEL_COORDINATOR", "deepseek-v4-flash"),
    # critic 证据评估：与 coordinator/knowledge_gap 同档位（便宜快的 flash）
    "critic": ("DEEPSEEK_MODEL_COORDINATOR", "deepseek-v4-flash"),
```
（仅新增一行 `"critic": ...`，其余不动。）

- [ ] **Step 4: 运行确认通过**

```bash
uv run pytest tests/test_model_factory_roles.py -v
```
Expected: 全部 PASS。

- [ ] **Step 5: AgentState 增加 4 个字段**

在 `backend/app/agent/graph/state.py` 里做两处编辑。

5.1 在 `Knowledge 产出` 段的 `is_enough: bool` 下方补 `max_score`：
```python
    # Knowledge 产出
    documents: list                     # list[str]
    citations: list                     # list[dict]，复用现有 citations 结构
    is_enough: bool
    max_score: float                    # 检索最高相关度；critic 评估证据 / 判断是否阈值过严
```

5.2 在文件末尾（`trace` 字段之后）追加 critic 回路字段：
```python
    # 轨迹（append-only）
    trace: Annotated[list, operator.add]

    # ── Critic 反馈回路（本计划新增）──
    # critic 触发改写重做时 +1，reducer 累加（与 trace/token_usage 一致，兼容并行）
    revision_count: Annotated[int, operator.add]
    # 最近一次 critic 输出 {verdict, reason, reformulated_query}；每次覆盖（无 reducer）
    critic_verdict: dict
    # critic 给出的改写 query；knowledge 重检索时优先用；每次覆盖（无 reducer）
    reformulated_query: str
```
（`Annotated`/`operator` 已在文件顶部导入，无需改 import。`TypedDict(total=False)` 使新字段均为可选；`critic_verdict`/`reformulated_query` 不带 reducer，按「最新一次为准」覆盖。）

- [ ] **Step 6: 行尾核查**

```bash
git diff --stat app/agent/graph/state.py app/utils/factory.py
git diff --stat --ignore-all-space app/agent/graph/state.py app/utils/factory.py
```
两者差距大则对该文件用 PowerShell 转回 CRLF：
```powershell
$f = "app/agent/graph/state.py"
$text = [System.Text.Encoding]::UTF8.GetString([System.IO.File]::ReadAllBytes($f))
$text = ($text -replace "`r`n", "`n") -replace "`n", "`r`n"
$utf8 = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($f, $text, $utf8)
```

- [ ] **Step 7: Commit**

```bash
git add app/agent/graph/state.py app/utils/factory.py tests/test_model_factory_roles.py
git commit -m "feat(graph): critic 回路基础设施——AgentState 新增 max_score/revision_count/critic_verdict/reformulated_query + factory critic 角色映射 flash"
```

---

## Task 2: critic_evidence 节点（结构化判定 + 异常降级 + 进度事件）

**目标：** 新建 `critic.py`，实现 `critic_node`：读 `query/history/documents/max_score`，用结构化输出产出三档 verdict（`relevant`/`needs_rewrite`/`out_of_scope`），异常/解析失败时降级为 `relevant`（不阻塞主路径）+ trace `failed`。本 Task **只写节点、不接路由**（路由在 Task 4），用单测验证。本 Task 的 critic prompt 还**不含 history**（history-aware 升级在 Task 5）。

**Files:**
- Create: `backend/app/agent/graph/nodes/critic.py`
- Test: `backend/tests/test_graph_critic_node.py`（新建）

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_graph_critic_node.py`:
```python
import pytest

from app.agent.graph.nodes.critic import CriticVerdict, critic_node, _verdict_to_dict


class _FakeMsg:
    usage_metadata = {"total_tokens": 55}


class _FakeStructuredModel:
    def __init__(self, result, captured):
        self.result = result
        self.captured = captured

    async def ainvoke(self, messages):
        self.captured["messages"] = messages
        return {"raw": _FakeMsg(), "parsed": self.result, "parsing_error": None}


class _FakeChatModel:
    def __init__(self, result, captured):
        self.result = result
        self.captured = captured

    def with_structured_output(self, schema, include_raw=False):
        self.captured["schema"] = schema
        self.captured["include_raw"] = include_raw
        return _FakeStructuredModel(self.result, self.captured)


def test_verdict_to_dict_normalizes_illegal_verdict():
    d = _verdict_to_dict({"verdict": "???", "reason": "x"})
    assert d["verdict"] == "relevant"


@pytest.mark.asyncio
async def test_critic_relevant_has_no_reformulation(monkeypatch):
    captured = {}
    result = CriticVerdict(verdict="relevant", reason="阈值过严", reformulated_query=None)

    import app.agent.graph.nodes.critic as cr
    monkeypatch.setattr(cr, "chat_model", _FakeChatModel(result, captured))

    update = await critic_node({"query": "年假几天", "documents": ["年假为5天"], "max_score": 0.3})
    assert update["critic_verdict"]["verdict"] == "relevant"
    assert "reformulated_query" not in update      # relevant 不带改写
    assert "revision_count" not in update           # relevant 不计 revision
    assert update["token_usage"] == 55
    assert update["trace"][0]["agent"] == "critic_evidence"
    assert update["trace"][0]["status"] == "done"


@pytest.mark.asyncio
async def test_critic_needs_rewrite_returns_reformulation(monkeypatch):
    captured = {}
    result = CriticVerdict(verdict="needs_rewrite", reason="指代未消解",
                           reformulated_query="2025版差旅报销上限")

    import app.agent.graph.nodes.critic as cr
    monkeypatch.setattr(cr, "chat_model", _FakeChatModel(result, captured))

    update = await critic_node({"query": "那它呢", "documents": [], "max_score": 0.1})
    assert update["critic_verdict"]["verdict"] == "needs_rewrite"
    assert update["reformulated_query"] == "2025版差旅报销上限"
    assert update["revision_count"] == 1            # 触发一次改写计数
    assert captured["schema"] is CriticVerdict
    assert captured["include_raw"] is True


@pytest.mark.asyncio
async def test_critic_degrades_to_relevant_on_llm_error(monkeypatch):
    import app.agent.graph.nodes.critic as cr

    class _Boom:
        def with_structured_output(self, *a, **k):
            class _S:
                async def ainvoke(self, _m):
                    raise RuntimeError("LLM down")
            return _S()

    monkeypatch.setattr(cr, "chat_model", _Boom())
    update = await critic_node({"query": "x", "documents": [], "max_score": None})
    assert update["critic_verdict"]["verdict"] == "relevant"   # 降级放行，不阻塞主路径
    assert update["trace"][0]["status"] == "failed"
    assert update["token_usage"] == 0


@pytest.mark.asyncio
async def test_critic_degrades_on_parsing_error(monkeypatch):
    import app.agent.graph.nodes.critic as cr

    class _StructParseErr:
        async def ainvoke(self, messages):
            return {"raw": None, "parsed": None, "parsing_error": ValueError("bad json")}

    class _Model:
        def with_structured_output(self, schema, include_raw=False):
            return _StructParseErr()

    monkeypatch.setattr(cr, "chat_model", _Model())
    update = await critic_node({"query": "x", "documents": [], "max_score": None})
    assert update["critic_verdict"]["verdict"] == "relevant"
    assert update["trace"][0]["status"] == "failed"
```

- [ ] **Step 2: 运行确认失败**

```bash
uv run pytest tests/test_graph_critic_node.py -v
```
Expected: FAIL —— `ModuleNotFoundError: No module named 'app.agent.graph.nodes.critic'`。

- [ ] **Step 3: 实现 critic 节点**

Create `backend/app/agent/graph/nodes/critic.py`:
```python
import json
from typing import Literal, Optional

from pydantic import BaseModel

from app.agent.graph._stream import safe_get_stream_writer
from app.agent.graph.state import AgentState
from app.utils.factory import chat_model, get_chat_model

_DEFAULT_CHAT_MODEL = chat_model

_CRITIC_PROMPT = """你是企业知识库 Agent 的检索证据评估器。系统已对用户问题做过一次知识库检索，但相关度未达阈值。请判断检索到的证据属于哪种情况。

只输出一个 JSON 对象，不要任何额外解释，格式：
{"verdict": "<relevant|needs_rewrite|out_of_scope>", "reason": "<简短中文理由>", "reformulated_query": "<改写后的查询；仅 needs_rewrite 时填写，否则为 null>"}

verdict 取值：
- relevant：证据其实足以回答，只是相关度阈值偏严，可直接据此作答
- needs_rewrite：问题表述/指代导致检索召回不准（如"那它呢"未消解、口语化、缺关键词），改写查询后有望召回——此时必须给出 reformulated_query
- out_of_scope：知识库确实没有相关内容，应如实告知用户并记录缺口

reformulated_query 要求：消解指代、补全主体与关键词、用更书面化的检索式表达；不要编造原文没有的限定条件。"""

# 异常/解析失败时的降级判定：放行（不阻塞主路径），由 finalize 兜底作答
_FALLBACK_VERDICT = {"verdict": "relevant", "reason": "critic 异常，降级放行", "reformulated_query": None}


class CriticVerdict(BaseModel):
    verdict: Literal["relevant", "needs_rewrite", "out_of_scope"]
    reason: str
    reformulated_query: Optional[str] = None


def _verdict_to_dict(obj: "CriticVerdict | dict") -> dict:
    """把结构化输出对象归一为状态中的 critic_verdict 字典；非法 verdict 归一为 relevant。"""
    data = obj.model_dump() if hasattr(obj, "model_dump") else dict(obj)
    verdict = data.get("verdict")
    if verdict not in ("relevant", "needs_rewrite", "out_of_scope"):
        verdict = "relevant"
    return {
        "verdict": verdict,
        "reason": str(data.get("reason", "")),
        "reformulated_query": data.get("reformulated_query"),
    }


def _build_messages(state: AgentState) -> list:
    documents = state.get("documents") or []
    if documents:
        evidence = "\n\n".join(f"【片段{i}】{d[:300]}" for i, d in enumerate(documents, 1))
    else:
        evidence = "（无检索结果）"
    user = (
        f"用户当前问题：{state['query']}\n"
        f"检索最高相关度：{state.get('max_score')}\n"
        f"检索到的证据片段：\n{evidence}"
    )
    return [
        {"role": "system", "content": _CRITIC_PROMPT},
        {"role": "user", "content": user},
    ]


async def critic_node(state: AgentState) -> dict:
    """对 is_enough=False 的检索结果做证据级评估（能改写救援 / 真超范围）。

    critic 走 with_structured_output().ainvoke() 返回完整对象——不经 messages 流，
    LLM token 不会被 astream 的 messages 模式捕获，也不会被 stream_bridge 放行给用户。
    """
    writer = safe_get_stream_writer()
    writer({"kind": "step", "id": "evidence_evaluating", "status": "running",
            "level": "info", "detail": "正在评估检索结果是否足以回答", "title": "评估检索证据"})

    messages = _build_messages(state)
    reformulated = None
    revision_inc = 0
    try:
        model = chat_model if chat_model is not _DEFAULT_CHAT_MODEL else get_chat_model("critic")
        structured = model.with_structured_output(CriticVerdict, include_raw=True)
        result = await structured.ainvoke(messages)
        if result.get("parsing_error"):
            raise result["parsing_error"]
        msg = result.get("raw")
        verdict = _verdict_to_dict(result["parsed"])
        if verdict["verdict"] == "needs_rewrite" and verdict.get("reformulated_query"):
            reformulated = verdict["reformulated_query"]
            revision_inc = 1
        status = "done"
        from app.agent.token_utils import extract_total_tokens, estimate_messages_tokens
        critic_tokens = extract_total_tokens(msg) or estimate_messages_tokens(messages)
    except Exception as e:
        from app.core.logger_handler import logger
        logger.error(f"[Critic] 证据评估失败，降级放行: {e}", exc_info=True)
        verdict = dict(_FALLBACK_VERDICT)
        status = "failed"
        critic_tokens = 0

    writer({"kind": "step", "id": "evidence_evaluated", "status": "done",
            "level": "success", "detail": f"证据评估：{verdict['verdict']}",
            "title": "已完成证据评估"})

    update = {
        "critic_verdict": verdict,
        "token_usage": critic_tokens,
        "trace": [{"agent": "critic_evidence", "status": status,
                   "output": json.dumps(verdict, ensure_ascii=False)}],
    }
    # 仅 needs_rewrite 时才写 reformulated_query / 累加 revision_count（reducer 要求 key 存在才累加）
    if reformulated:
        update["reformulated_query"] = reformulated
    if revision_inc:
        update["revision_count"] = revision_inc
    return update
```
> 说明：沿用 coordinator/knowledge_gap 的 `chat_model is not _DEFAULT_CHAT_MODEL` 守卫——单测 monkeypatch `cr.chat_model` 时走 fake，生产时走 `get_chat_model("critic")`（flash）。critic prompt 选用内联常量而非 `prompt_loader`，与同档位的 coordinator(`_COORDINATOR_PROMPT`)/knowledge_gap(`_GAP_PROMPT`) 风格一致（设计 §4 提及 prompt_loader，但 critic 需要按 state 动态拼 user 消息，内联更聚焦）。

- [ ] **Step 4: 运行确认通过**

```bash
uv run pytest tests/test_graph_critic_node.py -v
```
Expected: 5 个用例全 PASS。

- [ ] **Step 5: Commit**

（新建文件无需行尾核查。）
```bash
git add app/agent/graph/nodes/critic.py tests/test_graph_critic_node.py
git commit -m "feat(graph): 新增 critic_evidence 节点——结构化三档判定 + 异常降级放行 + 进度事件"
```

---

## Task 3: knowledge 节点支持 reformulated_query 重检索 + 暴露 max_score

**目标：** `knowledge_node` 检测到 `state["reformulated_query"]` 时用它替换 query 做检索（首检索仍用原 query），并把 `max_score` 写进返回 state（供 critic 评估）。重检索时发 `knowledge_refetching` 进度事件、trace agent 名记为 `knowledge_retry`（设计 §9）。本 Task 仍不接路由（路由在 Task 4），用单测验证节点行为。

**Files:**
- Modify: `backend/app/agent/graph/nodes/knowledge.py`
- Test: `backend/tests/test_graph_knowledge_refetch.py`（新建）

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_graph_knowledge_refetch.py`:
```python
import pytest

from app.agent.graph.nodes.knowledge import knowledge_node


@pytest.mark.asyncio
async def test_knowledge_uses_reformulated_query_on_retry(monkeypatch):
    captured = {}
    import app.agent.graph.nodes.knowledge as kn

    async def _fake_get(query, filter_meta=None):
        captured["query"] = query
        return {"documents": ["doc"], "citations": [{"filename": "a"}],
                "is_enough": True, "max_score": 0.9}

    monkeypatch.setattr(kn.rag_service, "get_documents_for_agent", _fake_get)

    update = await knowledge_node({"query": "那它呢", "identity": None,
                                   "reformulated_query": "2025版差旅报销上限"})
    assert captured["query"] == "2025版差旅报销上限"     # 重检索用改写后的 query
    assert update["max_score"] == 0.9                     # 暴露 max_score 供 critic
    assert update["is_enough"] is True
    assert update["trace"][0]["agent"] == "knowledge_retry"


@pytest.mark.asyncio
async def test_knowledge_first_pass_uses_original_query(monkeypatch):
    captured = {}
    import app.agent.graph.nodes.knowledge as kn

    async def _fake_get(query, filter_meta=None):
        captured["query"] = query
        return {"documents": [], "citations": [], "is_enough": False, "max_score": 0.1}

    monkeypatch.setattr(kn.rag_service, "get_documents_for_agent", _fake_get)

    update = await knowledge_node({"query": "原始问题", "identity": None})
    assert captured["query"] == "原始问题"               # 首检索用原 query
    assert update["max_score"] == 0.1
    assert update["trace"][0]["agent"] == "knowledge"     # 首检索 trace 名不变
```

- [ ] **Step 2: 运行确认失败**

```bash
uv run pytest tests/test_graph_knowledge_refetch.py -v
```
Expected: FAIL —— 当前 `knowledge_node` 不读 `reformulated_query`（仍用原 query）、返回里无 `max_score`、trace agent 恒为 `knowledge`。

- [ ] **Step 3: 改 knowledge_node**

把 `backend/app/agent/graph/nodes/knowledge.py` 的 `knowledge_node` 整体替换为：
```python
async def knowledge_node(state: AgentState) -> dict:
    """检索知识依据。权限 identity 从 state 取，绝不走隐式传递。

    若 state 带 reformulated_query（critic 改写救援），用它重检索；否则用原 query。
    """
    writer = safe_get_stream_writer()
    reformulated = state.get("reformulated_query")
    actual_query = reformulated or state["query"]
    is_retry = bool(reformulated)

    if is_retry:
        writer({"kind": "step", "id": "knowledge_refetching", "status": "running",
                "level": "info", "detail": f"改写后的查询：{actual_query[:30]}...",
                "title": "用更精细的查询重新检索"})
    else:
        writer({"kind": "step", "id": "tool_rag_summary_tools", "status": "running",
                "level": "info", "detail": "正在检索相关知识库", "title": "检索相关知识库"})

    identity = state.get("identity")
    node_status = "done"
    try:
        filter_meta = await _build_filter(identity)
        result = await rag_service.get_documents_for_agent(actual_query, filter_meta=filter_meta)
        documents = result.get("documents", [])
        citations = result.get("citations", [])
        # is_enough 由 rag_service 按缺口阈值（相关度）判定；缺字段时回退为"有无文档"，兼容旧返回/桩
        is_enough = result.get("is_enough", bool(documents))
        max_score = result.get("max_score")
    except Exception as e:
        from app.core.logger_handler import logger
        logger.error(f"[Knowledge] 检索失败，降级为空依据: {e}", exc_info=True)
        documents, citations, is_enough, max_score = [], [], False, None
        node_status = "failed"

    writer({"kind": "step",
            "id": "knowledge_refetching" if is_retry else "tool_rag_summary_tools",
            "status": "done", "level": "success",
            "detail": f"已检索 {len(citations)} 个文档", "title": "已检索知识库"})

    agent_name = "knowledge_retry" if is_retry else "knowledge"
    return {
        "documents": documents,
        "citations": citations,
        "is_enough": is_enough,
        "max_score": max_score,
        "trace": [{"agent": agent_name, "status": node_status,
                   "output": f"actual_query={actual_query} documents={len(documents)} "
                             f"is_enough={is_enough} max_score={max_score}"}],
    }
```

- [ ] **Step 4: 运行确认通过 + 不退化**

```bash
uv run pytest tests/test_graph_knowledge_refetch.py tests/test_graph_knowledge_node.py tests/test_graph_node_error_handling.py -v
```
Expected: 全部 PASS（新增重检索用例 + 既有 knowledge 节点/异常兜底用例不退化——它们传的 state 无 `reformulated_query`，走首检索分支，trace agent 仍为 `knowledge`）。

- [ ] **Step 5: 行尾核查**

```bash
git diff --stat app/agent/graph/nodes/knowledge.py
git diff --stat --ignore-all-space app/agent/graph/nodes/knowledge.py
```
差距大则用 Task 1 Step 6 的 PowerShell 片段转回 CRLF（把路径换成 `app/agent/graph/nodes/knowledge.py`）。

- [ ] **Step 6: Commit**

```bash
git add app/agent/graph/nodes/knowledge.py tests/test_graph_knowledge_refetch.py
git commit -m "feat(graph): knowledge 支持 reformulated_query 重检索并暴露 max_score（重检索 trace 记为 knowledge_retry）"
```

---

## Task 4: 接入条件路由 + 重做循环（build.py + 两个 router + 配置开关）

**目标：** 把 critic 真正接进图：`is_enough=False` 走 critic（开关开启时），critic 三档 verdict 路由到 task/finalize / 重检索 / gap，重检索回到 critic 再判一次，`max_revisions=1` 兜底。新增 `critic_config.py` 提供 `critic_enabled()`/`critic_max_revisions()`（独立模块，避免 task↔critic 循环导入）。**同步修复 3 个会被 critic 默认开启打破的既有路由测试。**

**Files:**
- Create: `backend/app/agent/graph/critic_config.py`
- Modify: `backend/app/agent/graph/nodes/critic.py`（追加 `route_after_critic`）
- Modify: `backend/app/agent/graph/nodes/task.py`（改 `route_after_knowledge`）
- Modify: `backend/app/agent/graph/build.py`（条件插入 critic 节点与边）
- Test: `backend/tests/test_graph_critic_routing.py`（新建）
- Test: `backend/tests/test_graph_build_critic.py`（新建）
- Test: `backend/tests/test_graph_gap_routing.py`（修：3 个用例适配 critic 默认开启）

- [ ] **Step 1: 写失败测试（两个 router）**

Create `backend/tests/test_graph_critic_routing.py`:
```python
from app.agent.graph.nodes.task import route_after_knowledge
from app.agent.graph.nodes.critic import route_after_critic


def test_route_after_knowledge_low_confidence_goes_to_critic(monkeypatch):
    monkeypatch.setenv("AGENT_CRITIC_ENABLE", "true")
    state = {"is_enough": False, "plan": {"task_type": "knowledge_qa"}}
    assert route_after_knowledge(state) == "critic"


def test_route_after_knowledge_critic_disabled_falls_back_to_gap(monkeypatch):
    monkeypatch.setenv("AGENT_CRITIC_ENABLE", "false")
    state = {"is_enough": False, "plan": {"task_type": "knowledge_qa"}}
    assert route_after_knowledge(state) == "knowledge_gap"


def test_route_after_knowledge_enough_qa_goes_to_finalize(monkeypatch):
    monkeypatch.setenv("AGENT_CRITIC_ENABLE", "true")
    state = {"is_enough": True, "plan": {"task_type": "knowledge_qa"}, "documents": ["d"]}
    assert route_after_knowledge(state) == "finalize"


def test_route_after_knowledge_enough_compare_goes_to_task(monkeypatch):
    monkeypatch.setenv("AGENT_CRITIC_ENABLE", "true")
    state = {"is_enough": True, "plan": {"task_type": "document_compare"}, "documents": ["d"]}
    assert route_after_knowledge(state) == "task"


def test_route_after_knowledge_coordinator_gap_still_gaps(monkeypatch):
    # coordinator 显式判 knowledge_gap 且 is_enough=True：仍直接走 gap（不进 critic）
    monkeypatch.setenv("AGENT_CRITIC_ENABLE", "true")
    state = {"is_enough": True, "plan": {"task_type": "knowledge_gap"}, "documents": ["d"]}
    assert route_after_knowledge(state) == "knowledge_gap"


def test_route_after_critic_relevant_to_finalize():
    state = {"critic_verdict": {"verdict": "relevant"},
             "plan": {"task_type": "knowledge_qa"}, "documents": ["d"]}
    assert route_after_critic(state) == "finalize"


def test_route_after_critic_relevant_compare_to_task():
    state = {"critic_verdict": {"verdict": "relevant"},
             "plan": {"task_type": "document_compare"}, "documents": ["d"]}
    assert route_after_critic(state) == "task"


def test_route_after_critic_needs_rewrite_within_budget(monkeypatch):
    monkeypatch.setenv("AGENT_CRITIC_MAX_REVISIONS", "1")
    # critic 已把 revision_count 累加到 1（≤ 上限）→ 重检索
    state = {"critic_verdict": {"verdict": "needs_rewrite"}, "revision_count": 1}
    assert route_after_critic(state) == "knowledge"


def test_route_after_critic_needs_rewrite_over_budget(monkeypatch):
    monkeypatch.setenv("AGENT_CRITIC_MAX_REVISIONS", "1")
    # 第二次仍 needs_rewrite，revision_count 累到 2（> 上限）→ 强制 gap
    state = {"critic_verdict": {"verdict": "needs_rewrite"}, "revision_count": 2}
    assert route_after_critic(state) == "knowledge_gap"


def test_route_after_critic_out_of_scope_to_gap():
    assert route_after_critic({"critic_verdict": {"verdict": "out_of_scope"}}) == "knowledge_gap"
```

- [ ] **Step 2: 运行确认失败**

```bash
uv run pytest tests/test_graph_critic_routing.py -v
```
Expected: FAIL —— `route_after_critic` 不存在（ImportError）；且 `route_after_knowledge` 尚不认识 `critic` 分支。

- [ ] **Step 3: 新建 critic_config.py**

Create `backend/app/agent/graph/critic_config.py`:
```python
"""Critic 回路的配置开关（env 驱动）。

独立成模块：build.py / task.py / critic.py 都要读它，
放这里避免 task ↔ critic 互相 import 形成循环。
"""
import os


def critic_enabled() -> bool:
    """critic 节点总开关；false/0/no 关闭后退化回现行单向流水线（紧急回退用）。"""
    return os.getenv("AGENT_CRITIC_ENABLE", "true").strip().lower() not in ("false", "0", "no")


def critic_max_revisions() -> int:
    """critic 触发改写重做的上限（默认 1，即最多改写一次）。"""
    try:
        return max(0, int(os.getenv("AGENT_CRITIC_MAX_REVISIONS", "1")))
    except ValueError:
        return 1
```

- [ ] **Step 4: critic.py 追加 route_after_critic**

在 `backend/app/agent/graph/nodes/critic.py` 末尾追加：
```python
def route_after_critic(state: AgentState) -> str:
    """critic 之后的三档路由：
    - relevant（或异常降级）：证据其实够用 → 恢复正常 task/finalize 选择
    - needs_rewrite 且未超改写上限 → knowledge 带 reformulated_query 重检索
    - needs_rewrite 已达上限 / out_of_scope → knowledge_gap
    """
    # 局部 import 取 TASK_TYPES：避免与 task.py 形成模块级循环依赖
    from app.agent.graph.nodes.task import TASK_TYPES_NEEDING_TASK
    from app.agent.graph.critic_config import critic_max_revisions

    verdict = (state.get("critic_verdict") or {}).get("verdict", "relevant")
    plan = state.get("plan") or {}

    if verdict == "needs_rewrite":
        # revision_count 已由 critic_node 累加；≤ 上限才允许这次重检索
        if state.get("revision_count", 0) <= critic_max_revisions():
            return "knowledge"
        return "knowledge_gap"
    if verdict == "out_of_scope":
        return "knowledge_gap"
    # relevant：恢复正常路由（有任务工具且有文档则走 task，否则 finalize）
    if plan.get("task_type") in TASK_TYPES_NEEDING_TASK and state.get("documents"):
        return "task"
    return "finalize"
```

- [ ] **Step 5: 改 route_after_knowledge（task.py）**

在 `backend/app/agent/graph/nodes/task.py` 顶部 import 区追加：
```python
from app.agent.graph.critic_config import critic_enabled
```
并把文件末尾的 `route_after_knowledge` 整体替换为：
```python
def route_after_knowledge(state: AgentState) -> str:
    """knowledge 之后的路由。

    is_enough=False：critic 开启则交给证据评估（可改写救援）；关闭则沿用原行为直接 gap。
    is_enough=True：coordinator 显式判 gap 优先；否则有任务工具且有文档走 task，余下 finalize。
    """
    plan = state.get("plan") or {}
    if not state.get("is_enough", True):
        return "critic" if critic_enabled() else "knowledge_gap"
    if plan.get("task_type") == "knowledge_gap":
        return "knowledge_gap"
    if plan.get("task_type") in TASK_TYPES_NEEDING_TASK and state.get("documents"):
        return "task"
    return "finalize"
```
> 注意：critic 关闭时，`not is_enough → knowledge_gap` 与 `task_type==knowledge_gap → knowledge_gap` 合起来等价于原实现（原为 `not is_enough or task_type==gap → gap`），行为不变。

- [ ] **Step 6: 运行 router 测试确认通过**

```bash
uv run pytest tests/test_graph_critic_routing.py -v
```
Expected: 10 个用例全 PASS。

- [ ] **Step 7: 写失败测试（build 接线）**

Create `backend/tests/test_graph_build_critic.py`:
```python
def test_build_graph_includes_critic_when_enabled(monkeypatch):
    monkeypatch.setenv("AGENT_CRITIC_ENABLE", "true")
    from app.agent.graph.build import build_graph
    g = build_graph()
    assert "critic" in g.nodes


def test_build_graph_omits_critic_when_disabled(monkeypatch):
    monkeypatch.setenv("AGENT_CRITIC_ENABLE", "false")
    from app.agent.graph.build import build_graph
    g = build_graph()
    assert "critic" not in g.nodes
```
> `CompiledStateGraph.nodes` 是节点名 → spec 的 dict（已验证含 `coordinator`/`knowledge`/`task`/`knowledge_gap`/`finalize` 等键）。

- [ ] **Step 8: 运行确认失败**

```bash
uv run pytest tests/test_graph_build_critic.py -v
```
Expected: FAIL —— 当前 `build_graph` 从不添加 `critic` 节点。

- [ ] **Step 9: 改 build.py 条件接线**

把 `backend/app/agent/graph/build.py` 整体替换为：
```python
from langgraph.graph import StateGraph, START, END

from app.agent.graph.state import AgentState
from app.agent.graph.critic_config import critic_enabled
from app.agent.graph.nodes.coordinator import coordinator_node, route_after_coordinator
from app.agent.graph.nodes.knowledge import knowledge_node
from app.agent.graph.nodes.task import task_node, route_after_knowledge
from app.agent.graph.nodes.knowledge_gap import knowledge_gap_node
from app.agent.graph.nodes.finalize import finalize_node
from app.agent.graph.nodes.critic import critic_node, route_after_critic


def build_graph():
    """多 agent 图（含可选 critic 反馈回路）：
    START → coordinator →(条件)→ knowledge|finalize
    knowledge →(条件)→ critic|knowledge_gap|task|finalize
    critic →(条件)→ knowledge(重检索)|knowledge_gap|task|finalize
    knowledge_gap → finalize；task → finalize；finalize → END

    AGENT_CRITIC_ENABLE=false 时不接 critic，退化回单向流水线。
    """
    g = StateGraph(AgentState)
    g.add_node("coordinator", coordinator_node)
    g.add_node("knowledge", knowledge_node)
    g.add_node("task", task_node)
    g.add_node("knowledge_gap", knowledge_gap_node)
    g.add_node("finalize", finalize_node)

    g.add_edge(START, "coordinator")
    g.add_conditional_edges(
        "coordinator",
        route_after_coordinator,
        {"knowledge": "knowledge", "finalize": "finalize"},
    )

    if critic_enabled():
        g.add_node("critic", critic_node)
        g.add_conditional_edges(
            "knowledge",
            route_after_knowledge,
            {"critic": "critic", "knowledge_gap": "knowledge_gap",
             "task": "task", "finalize": "finalize"},
        )
        g.add_conditional_edges(
            "critic",
            route_after_critic,
            {"knowledge": "knowledge", "knowledge_gap": "knowledge_gap",
             "task": "task", "finalize": "finalize"},
        )
    else:
        g.add_conditional_edges(
            "knowledge",
            route_after_knowledge,
            {"knowledge_gap": "knowledge_gap", "task": "task", "finalize": "finalize"},
        )

    g.add_edge("knowledge_gap", "finalize")
    g.add_edge("task", "finalize")
    g.add_edge("finalize", END)
    return g.compile()
```

- [ ] **Step 10: 运行 build 测试确认通过**

```bash
uv run pytest tests/test_graph_build_critic.py -v
```
Expected: 2 个用例 PASS。

- [ ] **Step 11: 修既有 test_graph_gap_routing.py（适配 critic 默认开启）**

`AGENT_CRITIC_ENABLE` 默认 `true`，会让「is_enough=False → 直接 gap」的 3 个既有用例改走 critic 而失败。这 3 个用例验证的是**critic 关闭时的回退路径**，给它们显式关掉 critic。

11.1 把 `test_route_to_gap_when_not_enough` 替换为：
```python
def test_route_to_gap_when_not_enough(monkeypatch):
    monkeypatch.setenv("AGENT_CRITIC_ENABLE", "false")   # critic 关闭时回退直连 gap
    state = {"plan": {"task_type": "knowledge_qa"}, "documents": [], "is_enough": False}
    assert route_after_knowledge(state) == "knowledge_gap"
```

11.2 把 `test_gap_priority_over_task` 替换为：
```python
def test_gap_priority_over_task(monkeypatch):
    monkeypatch.setenv("AGENT_CRITIC_ENABLE", "false")   # critic 关闭时回退直连 gap
    state = {"plan": {"task_type": "document_compare"}, "documents": [], "is_enough": False}
    assert route_after_knowledge(state) == "knowledge_gap"
```

11.3 在 `test_graph_routes_through_gap_node_when_no_docs` 函数体**最前面**（`import ...` 之前）加一行，让真图编译时也关掉 critic（该用例验证 critic 关闭时无依据直连 gap 节点落库）：
```python
async def test_graph_routes_through_gap_node_when_no_docs(monkeypatch):
    """is_enough=False（无文档）：critic 关闭时图应经过 knowledge_gap 节点，落库被调用。"""
    monkeypatch.setenv("AGENT_CRITIC_ENABLE", "false")
    import app.agent.graph.nodes.coordinator as co
    ...
```
（其余函数体不变；`build_graph()` 在函数内调用，会在 env 设好后读取。`test_route_to_gap_when_coordinator_says_gap`/`test_route_to_task_still_works`/`test_route_to_finalize_for_plain_qa` 均为 `is_enough=True`，不受影响，无需改。）

- [ ] **Step 12: 行尾核查**

```bash
git diff --stat app/agent/graph/nodes/critic.py app/agent/graph/nodes/task.py app/agent/graph/build.py
git diff --stat --ignore-all-space app/agent/graph/nodes/critic.py app/agent/graph/nodes/task.py app/agent/graph/build.py
```
差距大的文件用 Task 1 Step 6 的 PowerShell 片段逐个转回 CRLF。

- [ ] **Step 13: 局部回归 + Commit**

```bash
uv run pytest tests/test_graph_critic_routing.py tests/test_graph_build_critic.py tests/test_graph_gap_routing.py tests/test_graph_task_routing.py tests/test_graph_routing.py -v
```
Expected: 全部 PASS。然后：
```bash
git add app/agent/graph/critic_config.py app/agent/graph/nodes/critic.py app/agent/graph/nodes/task.py app/agent/graph/build.py tests/test_graph_critic_routing.py tests/test_graph_build_critic.py tests/test_graph_gap_routing.py
git commit -m "feat(graph): 接入 critic 条件路由与重做循环（max_revisions=1），新增 AGENT_CRITIC_ENABLE 开关"
```
> 说明：全局 `graph_runner` 单例在 `runner.py` import 时按当时 env 编译；生产默认 `AGENT_CRITIC_ENABLE=true` 即启用 critic。线上紧急回退 = 设 `AGENT_CRITIC_ENABLE=false` 后重启进程。

---

## Task 5: critic prompt 升级为 history-aware（多轮指代消解）

**目标：** 让 critic 看到最近一轮对话历史，把「那它 2025 版呢」这类指代正确消解后再判断「是否需要改写 query」。仅扩 critic 的 `_build_messages`，prompt 模板与判定逻辑不变。

**Files:**
- Modify: `backend/app/agent/graph/nodes/critic.py`（`_build_messages` 加最近一轮 history）
- Test: `backend/tests/test_graph_critic_node.py`（追加 1 个用例）

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_graph_critic_node.py` 末尾追加：
```python
@pytest.mark.asyncio
async def test_critic_prompt_includes_recent_history(monkeypatch):
    captured = {}
    result = CriticVerdict(verdict="needs_rewrite", reason="指代未消解",
                           reformulated_query="差旅2025版报销上限")

    import app.agent.graph.nodes.critic as cr
    monkeypatch.setattr(cr, "chat_model", _FakeChatModel(result, captured))

    await critic_node({
        "query": "那它2025版呢",
        "documents": [],
        "max_score": 0.1,
        "history": [("差旅2023版上限", "上限500元")],
    })
    user_content = captured["messages"][-1]["content"]
    assert "差旅2023版上限" in user_content and "那它2025版呢" in user_content
```

- [ ] **Step 2: 运行确认失败**

```bash
uv run pytest tests/test_graph_critic_node.py::test_critic_prompt_includes_recent_history -v
```
Expected: FAIL —— 当前 `_build_messages` 不读 history，user 消息里没有「差旅2023版上限」。

- [ ] **Step 3: 改 critic 的 _build_messages 加 history**

把 `backend/app/agent/graph/nodes/critic.py` 的 `_build_messages` 整体替换为：
```python
def _build_messages(state: AgentState) -> list:
    documents = state.get("documents") or []
    if documents:
        evidence = "\n\n".join(f"【片段{i}】{d[:300]}" for i, d in enumerate(documents, 1))
    else:
        evidence = "（无检索结果）"

    # 最近一轮历史用于指代消解判断（"那它呢" → 补全主体后再评估检索召回）
    history = state.get("history") or []
    history_text = ""
    if history and isinstance(history[-1], (list, tuple)) and len(history[-1]) == 2:
        last_u, last_a = history[-1]
        history_text = f"（上一轮——用户：{last_u}；助手：{last_a}）\n"

    user = (
        f"{history_text}用户当前问题：{state['query']}\n"
        f"检索最高相关度：{state.get('max_score')}\n"
        f"检索到的证据片段：\n{evidence}"
    )
    return [
        {"role": "system", "content": _CRITIC_PROMPT},
        {"role": "user", "content": user},
    ]
```
> 与 coordinator 一致只取最近一轮（设计 §7）：避免长历史干扰结构化 JSON 输出。

- [ ] **Step 4: 运行确认通过 + 不退化**

```bash
uv run pytest tests/test_graph_critic_node.py -v
```
Expected: 6 个用例全 PASS（含新增 history 用例与原 5 个）。

- [ ] **Step 5: 行尾核查 + Commit**

```bash
git diff --stat app/agent/graph/nodes/critic.py
git diff --stat --ignore-all-space app/agent/graph/nodes/critic.py
```
差距大则 PowerShell 转回 CRLF。然后：
```bash
git add app/agent/graph/nodes/critic.py tests/test_graph_critic_node.py
git commit -m "feat(graph): critic prompt 升级为 history-aware——注入最近一轮做指代消解"
```

---

## Task 6: finalize 防幻觉补丁（critic 判 relevant 时严格引用）

**目标：** 当 critic 把低置信 documents 判为 `relevant`（阈值过严但放行）时，给 finalize 补一条「严格只引用文档原文、不做推断、未覆盖的明确说明『文档未提及』」的指令，降低噪音误导风险（设计 §8 末段）。0 成本、不动任何不变量。

**Files:**
- Modify: `backend/app/agent/graph/nodes/finalize.py`（`_build_messages`）
- Test: `backend/tests/test_graph_finalize_node.py`（追加 2 个用例）

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_graph_finalize_node.py` 末尾追加：
```python
def test_finalize_injects_strict_citation_when_critic_relevant():
    from app.agent.graph.nodes.finalize import _build_messages
    msgs = _build_messages({
        "query": "年假几天",
        "documents": ["年假为5天"],
        "critic_verdict": {"verdict": "relevant"},
    })
    joined = " ".join(m["content"] for m in msgs)
    assert "文档未提及" in joined        # 注入了严格引用指令


def test_finalize_no_strict_citation_without_critic():
    from app.agent.graph.nodes.finalize import _build_messages
    msgs = _build_messages({"query": "年假几天", "documents": ["年假为5天"]})
    joined = " ".join(m["content"] for m in msgs)
    assert "文档未提及" not in joined    # 无 critic_verdict 时不注入
```

- [ ] **Step 2: 运行确认失败**

```bash
uv run pytest tests/test_graph_finalize_node.py::test_finalize_injects_strict_citation_when_critic_relevant -v
```
Expected: FAIL —— 当前 `_build_messages` 从不注入严格引用指令。

- [ ] **Step 3: 改 finalize 的 _build_messages**

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

    # 防幻觉：critic 把低置信 documents 判为 relevant（阈值过严）时，要求严格引用、不推断
    verdict = (state.get("critic_verdict") or {}).get("verdict")
    if verdict == "relevant":
        messages.append({"role": "user", "content":
            "请严格只引用文档原文片段作答，不要做推断或综合；"
            "文档未直接覆盖的部分，明确说明“文档未提及”。"})

    messages.append({"role": "user", "content": user})
    return messages
```

- [ ] **Step 4: 运行确认通过 + 不退化**

```bash
uv run pytest tests/test_graph_finalize_node.py -v
```
Expected: 全部 PASS（含新增 2 个与既有 finalize 用例）。

- [ ] **Step 5: 行尾核查 + Commit**

```bash
git diff --stat app/agent/graph/nodes/finalize.py
git diff --stat --ignore-all-space app/agent/graph/nodes/finalize.py
```
差距大则 PowerShell 转回 CRLF。然后：
```bash
git add app/agent/graph/nodes/finalize.py tests/test_graph_finalize_node.py
git commit -m "feat(graph): finalize 防幻觉补丁——critic 判 relevant 时注入严格引用指令"
```

---

## Task 7: 端到端验证 + 全量回归（含真图 critic 闭环）

**目标：** 用一条 committed e2e 测试跑通真编译图的 critic 闭环（低置信 → critic 判 needs_rewrite → 带改写重检索 → 命中 → finalize），断言 SSE 帧序列与 trace 摘要含 critic/重检索条目；再跑全量回归确认现有基线不退化。

**Files:**
- Test: `backend/tests/test_graph_critic_e2e.py`（新建）

- [ ] **Step 1: 写 e2e 测试**

Create `backend/tests/test_graph_critic_e2e.py`:
```python
import pytest

import app.agent.graph.nodes.coordinator as co
import app.agent.graph.nodes.knowledge as kn
import app.agent.graph.nodes.critic as cr
import app.agent.graph.nodes.finalize as fz
from app.agent.graph.nodes.coordinator import CoordinatorPlan
from app.agent.graph.nodes.critic import CriticVerdict
from app.agent.graph.runner import GraphRunner


class _Raw:
    usage_metadata = {"total_tokens": 10}


class _StructFake:
    def __init__(self, parsed):
        self._p = parsed

    async def ainvoke(self, messages):
        return {"raw": _Raw(), "parsed": self._p, "parsing_error": None}


class _ModelFake:
    def __init__(self, parsed):
        self._p = parsed

    def with_structured_output(self, schema, include_raw=False):
        return _StructFake(self._p)


class _FinalizeMsg:
    content = "这是基于改写检索后的最终回答"


class _FinalizeModel:
    async def ainvoke(self, messages):
        return _FinalizeMsg()


@pytest.mark.asyncio
async def test_critic_loop_end_to_end(monkeypatch):
    monkeypatch.setenv("AGENT_CRITIC_ENABLE", "true")
    monkeypatch.setenv("AGENT_CRITIC_MAX_REVISIONS", "1")

    monkeypatch.setattr(co, "chat_model", _ModelFake(
        CoordinatorPlan(task_type="knowledge_qa", need_retrieval=True, reason="问答")))
    monkeypatch.setattr(cr, "chat_model", _ModelFake(
        CriticVerdict(verdict="needs_rewrite", reason="指代未消解",
                      reformulated_query="2025版差旅报销上限")))
    monkeypatch.setattr(fz, "chat_model", _FinalizeModel())

    calls = {"n": 0}

    async def _fake_get(query, filter_meta=None):
        calls["n"] += 1
        if calls["n"] == 1:                      # 首检索：低置信
            return {"documents": [], "citations": [], "is_enough": False, "max_score": 0.1}
        return {                                  # 重检索：命中
            "documents": ["2025版差旅报销上限为800元"],
            "citations": [{"filename": "差旅2025.pdf", "score": 0.92}],
            "is_enough": True, "max_score": 0.92,
        }

    monkeypatch.setattr(kn.rag_service, "get_documents_for_agent", _fake_get)

    runner = GraphRunner()    # 在 env 设好后编译 → 启用 critic
    events = [e async for e in runner.stream(
        "那它2025版呢", history=[("差旅2023版上限", "上限500元")], identity=None)]

    # 进度帧含 critic 评估与重检索
    step_ids = [e["data"].get("id") for e in events if e["type"] == "agent_step_update"]
    assert "evidence_evaluating" in step_ids
    assert "knowledge_refetching" in step_ids

    # done.steps（trace 摘要）含 critic_evidence 与 knowledge_retry
    done = events[-1]
    assert done["type"] == "done"
    agents = [s["agent"] for s in done["steps"]]
    assert "critic_evidence" in agents
    assert "knowledge_retry" in agents

    # 确实重检索了一次（共两次检索调用）
    assert calls["n"] == 2

    # 用户最终看到回答（finalize 经 runner 兜底/流式产出）
    tokens = "".join(e["data"] for e in events if e["type"] == "token")
    assert tokens == "这是基于改写检索后的最终回答"
```
> 说明：fake finalize 用 `ainvoke` 不经 LangGraph 回调流 token，runner 的「无 token 兜底」会用最终 state 的 `final_answer` 补一帧（Phase 1 已建立），故 `tokens` 仍能拿到完整回答。critic/coordinator 的结构化输出走 fake，不调真实模型；identity=None 时 knowledge 不触发权限过滤，无需 DB。

- [ ] **Step 2: 运行 e2e 确认通过**

```bash
uv run pytest tests/test_graph_critic_e2e.py -v
```
Expected: PASS。若失败，**先按 systematic-debugging 定位**（常见点：`g.nodes`/custom 事件捕获、reducer 初值），不要改业务代码去迁就测试断言以外的预期。

- [ ] **Step 3: 全量回归**

```bash
uv run pytest tests/ -q
```
Expected: 全绿。重点确认设计 §11 列出的基线在 critic 默认开启下不退化：`test_agent_sse_steps` / `test_graph_runner_sse` / `test_kb_permissions` / `test_graph_finalize_node` / `test_graph_coordinator_node` / `test_graph_routing` / `test_graph_task_routing` / `test_graph_gap_routing`。失败原样贴报告，判断是否本次引入。

- [ ] **Step 4: 真实多轮 critic 闭环手验（由执行者直接运行，验证后删除）**

> 需要真实 LLM/RAG 凭据；若环境无凭据可跳过本步，仅以 Step 1-3 的自动化验证为准（在结论里注明跳过原因）。

Create `backend/_tmp_critic_verify.py`:
```python
import asyncio
from app.agent.graph.runner import graph_runner


async def main():
    q = "那它2025版改了什么"
    history = [("差旅2023版报销上限多少", "上限是500元")]
    events = []
    async for e in graph_runner.stream(q, history=history, identity=None):
        events.append(e)
    step_ids = [e["data"].get("id") for e in events if e["type"] == "agent_step_update"]
    tokens = "".join(e["data"] for e in events if e["type"] == "token")
    done = [e for e in events if e["type"] == "done"]
    print("step ids:", step_ids)
    print("回答前120字:", tokens[:120])
    print("done steps:", done[-1]["steps"] if done else None)
    print("done tokens:", done[-1]["tokens"] if done else None)


if __name__ == "__main__":
    asyncio.run(main())
```
运行：`PYTHONPATH=<backend绝对路径> uv run python _tmp_critic_verify.py`
预期：低置信问题会出现 `evidence_evaluating` 步；若触发改写则出现 `knowledge_refetching`，`done steps` 含 `critic_evidence`（必要时含 `knowledge_retry`）；回答体现「2025 版差旅」与上一轮的关联。验证后删除脚本：
```bash
rm _tmp_critic_verify.py    # PowerShell: Remove-Item _tmp_critic_verify.py
```

- [ ] **Step 5: 记录结论**

在本任务下方记录 `Critic 回路通过 / 问题`。通过即可按全局 worktree 流程 ff-merge 到 master。

---

## 已知限制（本计划范围内不处理，记录备查）

1. **不做答案级 critic**：仅评估检索证据，不评估 finalize 草稿质量（会破坏一次成型流式契约，需独立 spec）。设计 §13(1)。
2. **不做 Coordinator DAG 规划器**：coordinator 仍单选 task_type（Phase 3 #2，业务驱动后再做）。设计 §13(2)。
3. **`reformulated_query` 无人工兜底**：极端情况下改写可能比原 query 更差，靠 `max_revisions=1` 限制最多改写一次。设计 §14(2)。
4. **`AGENT_CRITIC_ENABLE` 仅全局开关**：无法按用户/会话粒度控制；全局 `graph_runner` 在 import 时编译，改开关需重启进程。设计 §14(3)。
5. **critic 仅看 documents 文本，不看 citations 元数据**：无法基于「文档版本/部门」等结构化字段判断（需等 chunk metadata 过滤通道）。设计 §14(1)。
6. **task_messages 路径不带 history / 不过 critic**：对比/报告/申请类任务的 is_enough=True 路径不经 critic（高置信直达 task），且其 messages 不含 history（沿用加固计划已知限制 #1）。
7. **新增进度事件文案前端零改动即可消费**：`evidence_evaluating`/`evidence_evaluated`/`knowledge_refetching` 复用现有 `agent_step_update` 帧，前端只是看到新的 id/title 文案。

---

## 计划自检

- **设计覆盖**：
  - §3 路由修正（删低分快速通道、is_enough=False 一律 critic、高置信跳过）→ Task 4（`route_after_knowledge`/`route_after_critic`/`build.py`）。
  - §4 节点划分（新增 critic flash、knowledge 小改）→ Task 2 + Task 3；配置项 `AGENT_CRITIC_ENABLE`/`AGENT_CRITIC_MAX_REVISIONS` → Task 4（`critic_config.py`）。
  - §5 状态扩展（revision_count/critic_verdict/reformulated_query，外加 critic 输入所需 max_score）→ Task 1。
  - §6 流式契约零改动 → critic 用 `with_structured_output().ainvoke()` 不经 messages 流（Task 2 实现 + Task 7 e2e 验证 token 仅 finalize 流出）。
  - §7 query 改写收进 critic + knowledge 重检索用 `reformulated_query`、coordinator/finalize 用原 query → Task 2/Task 3/Task 5。
  - §8 错误处理（critic 异常/解析失败降级 relevant + trace failed）→ Task 2；防幻觉补丁 → Task 6。
  - §9 可观测性（critic_evidence/knowledge_retry trace 条目、token_usage 自动累加、done 帧 trace 摘要）→ Task 2/Task 3，runner 无需改动（已有 `final_trace`/`token_usage` 通道）。
  - §10 渐进式 5 PR → 映射 Task 2(spike→正式节点)/Task 3+4(路由+重检索)/Task 5(history-aware)/Task 6(防幻觉)，外加基础设施 Task 1 与验证 Task 7。
  - §11 测试策略（critic 节点/路由/e2e 三类 + 回归基线）→ Task 2/4/7。
- **类型/命名一致**：`critic_verdict`（state 字段 / 节点 return key / 路由读取）、`reformulated_query`（critic 产出 / knowledge 消费）、`revision_count`（critic 累加 / `route_after_critic` 读取 `<= critic_max_revisions()`）、`max_score`（knowledge 产出 / critic 读取）、`critic_enabled`/`critic_max_revisions`（critic_config 定义 / build.py / task.py / critic.py 调用）、`route_after_critic`/`CriticVerdict`/`critic_node`（critic.py 定义 / build.py / 测试引用）前后一致。
- **既有测试冲突已处理**：critic 默认开启会改 `route_after_knowledge` 的 is_enough=False 行为，Task 4 Step 11 显式修了 `test_graph_gap_routing.py` 的 3 个相关用例（关掉 critic 验证回退路径）；其余基线为 is_enough=True 路径，不受影响。
- **无占位符**：每个含代码改动的 Step 均给出可直接套用的完整代码与确切命令；无 TBD / “类似上文” / “自行补充”。
- **导入环路核查**：`critic_config.py` 不 import 任何 graph 模块；`task.py` 仅 import `critic_config`；`critic.py` 的 `route_after_critic` 用局部 import 取 `task.TASK_TYPES_NEEDING_TASK` 与 `critic_config`——`task` 不 import `critic`，无模块级环路。
