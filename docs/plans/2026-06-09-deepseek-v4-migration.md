# DeepSeek V4 接入与分角色模型 实施计划

> **执行者须知（适用于任意能读写文件、运行命令的 AI 编码 agent —— Claude Code / Codex / Cursor 等均可）：** 本计划自包含，不依赖任何特定工具的私有能力或对话上下文。**Phase 0 是强制 spike**：DeepSeek + langchain 的若干真实行为（usage 字段、思考模式流式、参数兼容）必须先实测确认，再据其结论写/改后续代码——计划中凡标注「⚠️ spike 确认」处，是必须由实测定夺、不可凭猜测填写的点。每个含代码改动的步骤走 TDD：先写失败测试 → 确认失败 → 实现 → 确认通过 → 行尾核查 → commit。

**Goal:** 把 chat 引擎从 `ChatTongyi`（阿里云百炼）切换到 DeepSeek V4，并**按节点角色分配模型**（高频简单任务用便宜的 `v4-flash`、质量关键的最终生成用 `v4-pro`），在验证 tool-calling 稳定后落地结构化输出（原 #4-1）。

**Architecture:** 核心改造是 `factory.py` 从「单一全局 `chat_model`」升级为「**按角色取模型**」——因为分角色用不同模型 + 不同思考配置，需要多个实例。节点（coordinator/knowledge_gap/finalize）改为按自己的角色取模型。embedding 与 rerank 链完全不动（与 chat model 独立）。

**Tech Stack:** Python 3.12, LangGraph, `langchain-deepseek`（`ChatDeepSeek`，OpenAI 兼容）, 现有 `langchain-core`, pytest + pytest-asyncio。

**所有命令在 `backend/` 目录下用 `uv run` 执行。** 修改既有文件后做行尾核查（`git diff --numstat` vs `--ignore-all-space`，差距大用 PowerShell 转回 CRLF）。新建文件无需核查。

---

## 执行约定（环境与纪律，任意执行者先读）

- **工作目录**：除非另有说明，命令在 `backend/` 下执行。运行器用 `uv run`（无 uv 则用项目 venv 的 `python -m`）。`pyproject.toml` 的 `venv.path` warning 无害。
- **平台**：Windows + PowerShell；行尾核查核心约束是「改既有文件别把整文件 CRLF 翻成 LF」（diff 暴涨到几百行即中招）。
- **测试引擎隔离**：跑全量回归用 `AGENT_ENGINE=loop uv run pytest tests/ -q`（`test_agent_sse_steps.py` 假设 loop 引擎；详见仓库既有说明）。
- **TDD + 一 Task 一 commit**，message 用 `feat(model): …` / `refactor(factory): …`，附 `Co-Authored-By` 行。
- **改动面**：只改本 Task 列出的文件；计划与实际代码不符时以 Step 意图为准做最小适配并在 Task 末尾记一行。
- **密钥**：DeepSeek key 配在 `backend/.env`（gitignored），键名 `DEEPSEEK_API_KEY`；切勿提交 `.env`。

---

## 关键事实与依据（来自 DeepSeek 官方文档与 langchain，2026-06 核实）

| 事项 | 事实 | 出处 |
|---|---|---|
| 模型阵容 | `deepseek-v4-pro`（1.6T/49B active，对标顶级闭源，强 agentic/多文件）、`deepseek-v4-flash`（284B/13B，快且经济）。旧 `deepseek-chat`/`deepseek-reasoner` 2026/07/24 弃用 | DeepSeek pricing / V4 release |
| 定价（每 1M token） | flash：input miss $0.14 / output $0.28；pro：input miss $0.435 / output $0.87。**pro ≈ flash 的 3x** | DeepSeek pricing |
| 能力 | 两者**都**支持 JSON 输出 + tool calls（最多 128 函数、并行/多轮） | DeepSeek create-chat / V4 release |
| 思考模式 | **默认 enabled**；关闭用 `extra_body={"thinking":{"type":"disabled"}}`；思考内容经**独立 `reasoning_content` chunk** 流式返回 | DeepSeek thinking mode |
| 思考模式参数限制 | 思考模式**不支持** `temperature` / `top_p` / `presence_penalty` / `frequency_penalty` | DeepSeek thinking mode |
| langchain 集成 | `langchain_deepseek.ChatDeepSeek`；自定义参数走 `extra_body`（**不要用 `model_kwargs`，会报错**）；`ChatDeepSeek` 能正确暴露 `reasoning_content`（`ChatOpenAI` 会丢） | langchain-deepseek 文档 / issue #35059 |

> ⚠️ **现状冲突点**：当前 `factory.py` 给 `ChatTongyi`/`ChatOllama` 都传了 `top_p=0.7`。若 DeepSeek 开思考模式，`top_p` 会被拒/忽略——这是「关思考」的又一理由（见下表）。

---

## 模型分工方案（每条都有依据，非拍脑袋）

先厘清各节点的**调用频率**（来自代码）与**任务性质**：

| 节点 | 调用频率（代码事实） | 任务性质 | 是否直接调 LLM |
|---|---|---|---|
| `coordinator` | **每请求必调**（图入口） | 输出一个小 JSON 分类（`task_type`/`need_retrieval`/`reason`） | 是 |
| `knowledge_gap` | 仅 `is_enough=False` 时 | 输出结构化缺口 JSON（title/category/suggested_content） | 是 |
| `finalize` | **每请求必调**（唯一用户可见 token 出口） | 最终回答；对比表/报告/申请等复杂生成也在此 | 是 |
| `task`（compare/report/form） | 仅对应任务时 | **只 `build_messages` 构造 prompt，不调 LLM**（生成交给 finalize） | 否 |

### 选型表

| 角色 | 选型 | 思考 | 依据（可追溯） |
|---|---|---|---|
| **coordinator** | `v4-flash` | **disabled** | ① 每请求必调→高频，成本敏感，flash 比 pro 便宜约 3x；② 任务是简单分类，不需长链推理；③ 要稳定吐 JSON，关思考更快更省（思考 token 计入 output）；④ 关思考后可正常用 `top_p`，与现有配置兼容 |
| **knowledge_gap** | `v4-flash` | **disabled** | ① 频率低但任务简单（结构化缺口），flash 足够；② 同样要 JSON 输出，关思考更直接 |
| **finalize** | `v4-pro` | **disabled（一期）** | ① 产出用户可见最终答案 + 报告/对比/申请等复杂生成，质量关键→pro 的强生成能力；② 但 RAG 是**基于检索片段的 grounded 作答**，不是开放式推理，长链思考收益低、而 pro 的 output 是 $0.87/1M（思考 token 也算 output）→关思考省成本省延迟；③ 关思考则流式无需处理 `reasoning_content`，不破坏现有「唯一 token 出口」契约 |
| `task` 节点 | —— | —— | 不调 LLM，无需选型；其生成质量由 `finalize` 的模型决定 |

> **未来可选**：若出现确需深度推理的任务（如多文档深度对比分析），可针对该 `task_type` 单独让 finalize 开思考模式——但需届时处理 `reasoning_content` 流式与 `top_p` 限制，**一期不做**。

> **embedding / rerank 不在此列**：检索用 `embed_model`（Ollama/阿里云 DashScope）、rerank 用阿里云 `qwen3-vl-rerank`，与 chat model 独立，本计划完全不动。DeepSeek 不提供 embedding，别试图用它替代。

---

## Phase 0：Spike（强制第一步，不通过则不继续）

**目的**：用最小代价实测 DeepSeek + langchain 的真实行为，把后续所有「⚠️ spike 确认」点定下来。**这是一次性探索脚本，由执行者直接运行，跑完删除。**

**前置**：`backend/.env` 配好 `DEEPSEEK_API_KEY`；`uv add langchain-deepseek`（或 `uv pip install langchain-deepseek`）。

- [ ] **Step 1: 写 spike 脚本**

Create `backend/_tmp_deepseek_spike.py`：
```python
import asyncio
import os
from langchain_deepseek import ChatDeepSeek

KEY = os.getenv("DEEPSEEK_API_KEY")


def make(model, thinking):
    return ChatDeepSeek(
        model=model,
        api_key=KEY,
        streaming=True,
        extra_body={"thinking": {"type": thinking}},
    )


async def probe(model, thinking):
    print(f"\n=== {model} thinking={thinking} ===")
    llm = make(model, thinking)
    # 1) 非流式 invoke：看 usage 与 reasoning_content 暴露位置
    msg = await llm.ainvoke([{"role": "user", "content": "用一句话说明请假流程"}])
    print("content:", (msg.content or "")[:80])
    print("usage_metadata:", getattr(msg, "usage_metadata", None))
    print("additional_kwargs keys:", list(getattr(msg, "additional_kwargs", {}).keys()))
    print("response_metadata keys:", list(getattr(msg, "response_metadata", {}).keys()))
    # 2) 流式：看 reasoning_content 是否混进 content / 在哪个字段
    print("--- stream chunks (前若干) ---")
    n = 0
    async for ch in llm.astream([{"role": "user", "content": "1+1=? 简短回答"}]):
        ak = getattr(ch, "additional_kwargs", {})
        print("chunk.content=", repr(ch.content), "| additional_kwargs=", ak)
        n += 1
        if n >= 8:
            break


async def main():
    await probe("deepseek-v4-flash", "disabled")
    await probe("deepseek-v4-pro", "disabled")
    await probe("deepseek-v4-pro", "enabled")   # 对照：看思考开启时 reasoning_content 形态


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: 运行并记录结论（4 个必答问题）**

Run: `uv run python _tmp_deepseek_spike.py`

把以下结论**写进本 Task 下方**（后续 Step 依赖它们）：
1. **usage**：`disabled` 模式下 `usage_metadata.total_tokens` 是否有值？→ 决定 `#8` 的 `extract_total_tokens` 是否照常生效（目标：`estimated=False`）。
2. **reasoning_content（关思考）**：`thinking=disabled` 时流式 chunk 是否**完全没有** `reasoning_content`、`content` 是否纯净？→ 这是「finalize 关思考即可不破坏 token 流」的前提。
3. **reasoning_content（开思考，对照）**：开启时 `reasoning_content` 出现在 chunk 的哪个字段（`additional_kwargs['reasoning_content']`？）→ 备将来可选开思考时用。
4. **参数兼容**：`disabled` + 传 `top_p=0.7` 是否报错？（在 `make()` 里加 `top_p=0.7` 再跑一次）→ 决定 factory 是否保留 `top_p`。

**实测结论（2026-06-09，langchain-deepseek 1.0.1）：**
1. **usage**：`thinking=disabled` 下 `deepseek-v4-flash` 与 `deepseek-v4-pro` 的 `usage_metadata.total_tokens` 均有值；可继续使用 `extract_total_tokens`，目标为 `estimated=False`。
2. **reasoning_content（关思考）**：`thinking=disabled` 的流式 chunk 未出现 `reasoning_content`，`content` 只包含最终答复 token，纯净。
3. **reasoning_content（开思考，对照）**：`thinking=enabled` 时，非流式消息的 `additional_kwargs["reasoning_content"]` 包含完整思考内容；流式 chunk 的思考片段也出现在 `additional_kwargs["reasoning_content"]`，对应 chunk 的 `content` 为空，最终答复 token 才进入 `content`。
4. **参数兼容**：`thinking=disabled` + `top_p=0.7` 实测不报错，`usage_metadata.total_tokens` 仍有值，流式 content 仍纯净；factory 可保留 `top_p=0.7`。
5. **判定**：问题 1 与问题 2 均为「是」，允许继续 Phase 1。

- [ ] **Step 3: 删除 spike 脚本**

`rm backend/_tmp_deepseek_spike.py`。spike 结论已记录，脚本不入库。

**判定**：若问题 1（usage 可得）与问题 2（关思考后 content 纯净）均为「是」→ 继续 Phase 1；若为「否」→ 停下来上报，重新评估选型（如改用别的访问格式或保留 ChatTongyi）。

---

## Phase 1：factory 分角色 + 节点接入

**目标**：`factory.py` 支持 `LLM_TYPE=DEEPSEEK`，并提供**按角色取模型**的接口；节点按角色取模型。其他 `LLM_TYPE`（ALIYUN/OLLAMA）保持单模型行为不变（向后兼容）。

**Files:**
- Modify: `backend/app/utils/factory.py`
- Modify: `backend/app/agent/graph/nodes/coordinator.py`、`knowledge_gap.py`、`finalize.py`（改模型来源）
- Test: `backend/tests/test_model_factory_roles.py`（新建）

### 角色→模型映射（env 驱动，给默认值）

`.env` 新增（值为建议默认，来自上文选型表）：
```
LLM_TYPE=DEEPSEEK
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL_COORDINATOR=deepseek-v4-flash
DEEPSEEK_MODEL_FINALIZE=deepseek-v4-pro
```

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_model_factory_roles.py`：
```python
from app.utils.factory import get_chat_model


def test_get_chat_model_returns_instance_for_each_role():
    for role in ("coordinator", "knowledge_gap", "finalize"):
        m = get_chat_model(role)
        assert m is not None
        # 同一角色多次取应是同一实例（单例缓存，避免重复构造）
        assert get_chat_model(role) is m


def test_unknown_role_falls_back_to_finalize():
    assert get_chat_model("不存在的角色") is get_chat_model("finalize")
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_model_factory_roles.py -v` → Expected: `ImportError: cannot import name 'get_chat_model'`。

- [ ] **Step 3: 实现 `get_chat_model(role)`**

在 `factory.py` 增加（保留现有 `chat_model = ChatModelFactory().generator()` 作为默认/兼容；新增按角色获取）：
```python
from functools import lru_cache

# 角色 → env 中的模型名键（仅 DEEPSEEK 用；其他 LLM_TYPE 所有角色复用默认 chat_model）
_DEEPSEEK_ROLE_ENV = {
    "coordinator": ("DEEPSEEK_MODEL_COORDINATOR", "deepseek-v4-flash"),
    "knowledge_gap": ("DEEPSEEK_MODEL_COORDINATOR", "deepseek-v4-flash"),
    "finalize": ("DEEPSEEK_MODEL_FINALIZE", "deepseek-v4-pro"),
}


@lru_cache(maxsize=None)
def get_chat_model(role: str = "finalize"):
    """按节点角色取 chat 模型。DEEPSEEK 下按角色分配 flash/pro 并关思考；
    其他 LLM_TYPE 一律复用全局默认 chat_model（向后兼容）。"""
    llm_type = os.getenv("LLM_TYPE", "ALIYUN").upper()
    if llm_type != "DEEPSEEK":
        return chat_model  # 现有 ChatTongyi/ChatOllama 单例
    from langchain_deepseek import ChatDeepSeek
    env_key, default_model = _DEEPSEEK_ROLE_ENV.get(role, _DEEPSEEK_ROLE_ENV["finalize"])
    model_name = os.getenv(env_key, default_model)
    return ChatDeepSeek(
        model=model_name,
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        streaming=True,
        extra_body={"thinking": {"type": "disabled"}},   # 一期全角色关思考（依据见选型表）
        # ⚠️ spike 确认：top_p 在 disabled 下若不报错则加回 top_p=0.7；报错则不传
    )
```
> ⚠️ 上面 `top_p` 与 `ChatDeepSeek` 构造参数名以 **Phase 0 spike 结论**为准。还需让 `LLM_TYPE=DEEPSEEK` 时全局 `chat_model`（仍被 `agent_tools` 等旧路径引用）也指向一个可用 deepseek 实例——最简：把模块底部 `chat_model` 的赋值也纳入 DEEPSEEK 分支（在 `ChatModelFactory.generator()` 里加 `DEEPSEEK` 分支返回 finalize 档模型）。

- [ ] **Step 4: 节点改为按角色取模型**

把三个节点里的 `from app.utils.factory import chat_model` + `chat_model.ainvoke(...)` 改为按角色取：
- `coordinator.py`：模块顶部 `from app.utils.factory import get_chat_model`，调用处 `await get_chat_model("coordinator").ainvoke(messages)`。
- `knowledge_gap.py`：`get_chat_model("knowledge_gap")`。
- `finalize.py`：`get_chat_model("finalize")`。

> 保持各节点其余逻辑（#5/#6/#8 的改动）不变。注意 `finalize` 的 token 流来自 LangGraph `messages` 模式，模型实例换了不影响 `stream_bridge` 的 `langgraph_node=="finalize"` 过滤。

- [ ] **Step 5: 运行测试 + loop 引擎全量回归**

```bash
uv run pytest tests/test_model_factory_roles.py -v
AGENT_ENGINE=loop uv run pytest tests/ -q
```
Expected：新测试通过；既有 graph 单测（用 monkeypatch 注入假 chat_model 的）仍绿——⚠️ 若有测试直接 patch `factory.chat_model` 而非节点导入的符号，可能因改用 `get_chat_model` 而失配，需把这些测试的 patch 目标改为 `get_chat_model`（最小适配，记录在 Task 末尾）。

- [ ] **Step 6: 行尾核查 + Commit**

```bash
git add app/utils/factory.py app/agent/graph/nodes/coordinator.py app/agent/graph/nodes/knowledge_gap.py app/agent/graph/nodes/finalize.py tests/test_model_factory_roles.py
git commit -m "feat(model): 接入 DeepSeek V4 并按角色分配模型（coordinator/gap=flash, finalize=pro，关思考）"
```

- [ ] **Step 7: 真实端到端验证（由执行者直接运行）**

复用既有验证手法跑一次真实多轮 query（仿之前 `_tmp_phase1_verify.py`），确认：
1. 回答正常、多轮指代生效；
2. `done.tokens` 的 `estimated=False`（DeepSeek usage 被 `extract_total_tokens` 抓到）；
3. **finalize token 流中没有思考内容泄漏**（关思考生效）。
验证后删除临时脚本，记录结论。

**实测结论（2026-06-09）：** 使用 `LLM_TYPE=DEEPSEEK` 运行 `GraphRunner.stream`，历史为「我叫小李...」，当前问题为「那我叫什么？请简短回答。」；输出为「你叫小李。」，多轮指代生效；`done.tokens=850`，来自图内 coordinator/finalize 节点的精确 `usage_metadata.total_tokens` 累计；finalize token 流未出现 `reasoning_content` 或思考文本泄漏。

---

## Phase 2：结构化输出（原 #4-1，依赖 Phase 0/1 通过）

**前提**：Phase 0 已确认 DeepSeek tool-calling/JSON 稳定可用。此前在 ChatTongyi 上「不做」的唯一理由（provider 不稳）已消除。

**目标**：`coordinator` / `knowledge_gap` 改用 `with_structured_output(schema)` 替代正则抠 JSON，删除 `_parse_plan`/`_parse_gap` 的正则与兜底分支（保留 `#6` 的异常兜底：结构化调用失败时仍降级到 `_FALLBACK_PLAN`/`_fallback_gap`）。

**Files:** Modify `coordinator.py`、`knowledge_gap.py`；改对应单测。

- [ ] **Step 1: 为 coordinator 定义 Pydantic schema + 改测试**

新增 schema（如 `class CoordinatorPlan(BaseModel): task_type: Literal[...]; need_retrieval: bool; reason: str`）。把 `test_graph_coordinator_node.py` 中针对 `_parse_plan` 文本解析的用例，改为针对「结构化输出对象 → plan dict」的用例（mock 模型 `with_structured_output` 的返回）。

- [ ] **Step 2: 运行确认失败 → 实现 → 确认通过**

`coordinator_node` 改为 `structured = get_chat_model("coordinator").with_structured_output(CoordinatorPlan)`，`plan_obj = await structured.ainvoke(messages)`，再转 dict；`except` 分支保留 `_FALLBACK_PLAN`（#6 不变）。`knowledge_gap` 同法。

> ⚠️ `with_structured_output` 与 `extra_body` thinking 的兼容性以 spike/实测为准；结构化输出本就不需要思考，确保该路径 `thinking=disabled`。

**实测结论（2026-06-09，langchain-deepseek 1.0.1）：** `deepseek-v4-flash` + `thinking=disabled` + `top_p=0.7` 调用 `with_structured_output(PydanticSchema, include_raw=True)` 成功；返回包含 `raw`、`parsed`、`parsing_error`，`parsed` 为 Pydantic 对象，`raw.usage_metadata.total_tokens` 有值，`raw.additional_kwargs` 无 `reasoning_content`。

- [ ] **Step 3: 全量回归 + 行尾核查 + Commit**

```bash
AGENT_ENGINE=loop uv run pytest tests/ -q
git commit -m "refactor(graph): coordinator/knowledge_gap 改用结构化输出，移除正则解析"
```

---

## 风险与坑（务必在执行中盯住）

1. **思考模式流式泄漏**（最高风险）：若任何角色误开思考，`reasoning_content` 会进入流；finalize 一旦泄漏，用户会看到模型「想」的过程，且 `stream_bridge` 需相应处理。**一期对策：全角色 `thinking=disabled`**，并在 Phase 0/1 实测确认 content 纯净。
2. **`top_p` 等参数**：思考模式不支持 `top_p`/`temperature` 等；现有 factory 传 `top_p=0.7`。关思考后能否传 `top_p` 以 spike 为准（Phase 0 问题 4）。
3. **usage 字段**：必须实测 `estimated=False`，否则 `#8` 退回估算。
4. **测试 monkeypatch 目标**：既有 graph 单测若直接 patch `factory.chat_model`，改用 `get_chat_model` 后要把 patch 目标对齐（否则假失败）。
5. **embedding 不被替代**：DeepSeek 无 embedding，检索链不动，别误改。
6. **成本**：finalize 用 pro（output $0.87/1M）。若上线后成本偏高，可评估 finalize 也降到 flash（质量/成本权衡），但需对比答案质量后再定。

---

## 非目标（本计划不做）

- 不动 embedding / rerank / 向量库。
- 不做投机检索降延迟（属另一份计划的 Phase 3 图编排改造）。
- 不做分类结果缓存（与多轮 history 的指代消解冲突）。
- 一期不为任何角色开启思考模式（保留为未来按 task_type 的可选增强）。

---

## 计划自检

- **依据可追溯**：模型分工每条依据可回溯到（调用频率=代码事实 / 定价 3x=DeepSeek 官方 / 思考成本与参数限制=DeepSeek thinking 文档 / langchain extra_body 用法=langchain-deepseek 文档）。
- **不确定即标注**：凡 DeepSeek+langchain 的运行时行为（usage 字段、reasoning_content 位置、top_p 兼容、with_structured_output 行为）均标「⚠️ spike 确认」，由 Phase 0 实测定夺，不在计划里猜死。
- **向后兼容**：`LLM_TYPE!=DEEPSEEK` 时 `get_chat_model` 退回现有 `chat_model`，不影响 ALIYUN/OLLAMA 用户。
