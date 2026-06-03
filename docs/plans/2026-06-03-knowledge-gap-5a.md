# Phase 5a：知识缺口（后端）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在检索不足或被判定为缺口类问题时，生成结构化知识缺口记录落库（带去重），并经 finalize 流式如实告知用户，同时提供查询/改状态的 API。

**Architecture:** 新增 `knowledge_gaps` 表 + `knowledge_gap_service`（单例 + AsyncSessionLocal，仿 `document_service`）。新增 `KnowledgeGap` 图节点：调一次 LLM 生成结构化缺口内容 → 落库 → 写 `state["task_messages"]` 让 finalize 流式告知（复用 Phase 4 机制）。扩展 `route_after_knowledge`：缺口判断优先于 task。新增两个 CRUD API。

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 async（AsyncSessionLocal + run_sync）, LangGraph 1.1.6, FastAPI, 现有 `chat_model`, pytest + pytest-asyncio + aiosqlite。

**前置（已在 master 59da269）：** 图 `coordinator→knowledge→(task|finalize)`；`finalize` 用 `state["task_messages"]`；`knowledge` 产 `is_enough=bool(documents)`；`coordinator` 产 `plan.task_type`（含 `knowledge_gap`）；`nodes/task.py` 有 `route_after_knowledge` 与 `TASK_TYPES_NEEDING_TASK`；`_stream.safe_get_stream_writer`；模型在 `models/chat_history.py`（`Base`）；service 仿 `services/document_service.py`（`async with AsyncSessionLocal() as db` + `await db.run_sync(lambda s: s.query(...)...)`）；API 在 `router/chat.py`（`success_response`、`get_current_identity` → `RequestIdentity(user_id, is_admin, dept_id, is_dept_admin)`）；测试 conftest 有 `sqlite_db` fixture（用 SQLite 内存库 + `Base.metadata.create_all`，monkeypatch `kb_service.AsyncSessionLocal`）。

**所有命令在 `backend/` 目录下用 `uv run`。** uv 命令的 `pyproject.toml:66 venv.path` warning 无害，忽略。修改既有文件（chat_history.py / task.py / build.py / chat.py）必须行尾核查（`git diff --stat` vs `--ignore-all-space`，差距大用 PowerShell 转回 CRLF）。

**为什么没有 spike：** 不引入新机制（LangGraph 节点/条件边、task_messages 流式、SQLAlchemy async service、FastAPI 路由都已在用），直接 TDD。

**范围：** 仅后端（5a）。前端缺口页是 5b，另开计划。

---

## 文件结构

新建：
- `backend/app/services/knowledge_gap_service.py` — 缺口落库/查询/改状态 service（单例）
- `backend/app/agent/graph/nodes/knowledge_gap.py` — KnowledgeGap 节点（LLM 生成 + 落库 + task_messages）
- `backend/tests/test_knowledge_gap_service.py`
- `backend/tests/test_graph_knowledge_gap_node.py`
- `backend/tests/test_graph_gap_routing.py`
- `backend/tests/test_knowledge_gap_api.py`

修改：
- `backend/app/models/chat_history.py` — 新增 `KnowledgeGap` model
- `backend/app/agent/graph/nodes/task.py` — 扩展 `route_after_knowledge`（缺口分支优先）
- `backend/app/agent/graph/build.py` — 接入 knowledge_gap 节点
- `backend/app/router/chat.py` — 新增两个缺口 API

---

## Task 1: knowledge_gaps 表 model

**Files:**
- Modify: `backend/app/models/chat_history.py`

- [ ] **Step 1: 在 chat_history.py 末尾追加 KnowledgeGap model**

在 `backend/app/models/chat_history.py` 文件末尾追加（文件顶部已 `from sqlalchemy import ... Integer, String, Text, DateTime ...` 与 `from sqlalchemy.sql import func`、`Base = declarative_base()`，直接复用）：
```python


class KnowledgeGap(Base):
    """知识缺口记录：检索不足或被判定为缺口类问题时生成，供管理员补充知识库。"""
    __tablename__ = "knowledge_gaps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)   # 缺口产生者
    dept_id = Column(String(64), nullable=True, index=True)    # 部门归属（备用）
    title = Column(String(255), nullable=False)
    question = Column(Text, nullable=False)                    # 去重键之一
    category = Column(String(64), default="unknown")
    suggested_content = Column(Text, default="")
    status = Column(String(20), nullable=False, default="pending")  # pending/reviewed/resolved/ignored
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 2: 验证可导入 + 字段齐全**

Run:
```bash
uv run python -c "from app.models.chat_history import KnowledgeGap; print(KnowledgeGap.__tablename__, sorted(c.name for c in KnowledgeGap.__table__.columns))"
```
Expected: 打印 `knowledge_gaps ['category', 'created_at', 'dept_id', 'id', 'question', 'status', 'suggested_content', 'title', 'updated_at', 'user_id']`。

- [ ] **Step 3: 行尾核查**

```bash
git diff --stat app/models/chat_history.py
git diff --stat --ignore-all-space app/models/chat_history.py
```
差距大则 PowerShell 转回 CRLF：
```powershell
$f = "app/models/chat_history.py"
$text = [System.Text.Encoding]::UTF8.GetString([System.IO.File]::ReadAllBytes($f))
$text = ($text -replace "`r`n", "`n") -replace "`n", "`r`n"
$utf8 = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($f, $text, $utf8)
```

- [ ] **Step 4: Commit**

```bash
git add app/models/chat_history.py
git commit -m "feat: 新增 knowledge_gaps 表 model"
```

---

## Task 2: knowledge_gap_service（去重 / 过滤 / 越权防护）

**Files:**
- Create: `backend/app/services/knowledge_gap_service.py`
- Test: `backend/tests/test_knowledge_gap_service.py`

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_knowledge_gap_service.py`:
```python
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.models.chat_history import Base


@pytest_asyncio.fixture
async def gap_db(monkeypatch):
    """SQLite 内存库替换 knowledge_gap_service 的 AsyncSessionLocal。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    import app.services.knowledge_gap_service as mod
    monkeypatch.setattr(mod, "AsyncSessionLocal", Session)
    yield Session
    await engine.dispose()


@pytest.mark.asyncio
async def test_save_then_list(gap_db):
    from app.services.knowledge_gap_service import knowledge_gap_service as svc
    await svc.save_gap("u1", "d1", "设备报销", "远程办公设备损坏怎么报销", "财务", "建议补充1.2.3")
    gaps = await svc.list_gaps("u1", is_admin=False)
    assert len(gaps) == 1
    assert gaps[0]["title"] == "设备报销" and gaps[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_dedup_same_question_pending(gap_db):
    from app.services.knowledge_gap_service import knowledge_gap_service as svc
    await svc.save_gap("u1", None, "T", "同一个问题", "c", "s1")
    await svc.save_gap("u1", None, "T2", "同一个问题", "c", "s2")
    gaps = await svc.list_gaps("u1", is_admin=False)
    assert len(gaps) == 1   # 去重：未新增


@pytest.mark.asyncio
async def test_list_filters_by_user_for_non_admin(gap_db):
    from app.services.knowledge_gap_service import knowledge_gap_service as svc
    await svc.save_gap("u1", None, "T", "问题A", "c", "s")
    await svc.save_gap("u2", None, "T", "问题B", "c", "s")
    assert len(await svc.list_gaps("u1", is_admin=False)) == 1
    assert len(await svc.list_gaps("u1", is_admin=True)) == 2   # 管理员看全部


@pytest.mark.asyncio
async def test_update_status_and_permission(gap_db):
    from app.services.knowledge_gap_service import knowledge_gap_service as svc
    await svc.save_gap("u1", None, "T", "问题X", "c", "s")
    gid = (await svc.list_gaps("u1", is_admin=False))[0]["id"]
    assert await svc.update_status(gid, "u1", is_admin=False, status="resolved") is True
    assert (await svc.list_gaps("u1", is_admin=True))[0]["status"] == "resolved"
    # 越权：他人非管理员改 → PermissionError
    with pytest.raises(PermissionError):
        await svc.update_status(gid, "u2", is_admin=False, status="ignored")


@pytest.mark.asyncio
async def test_update_status_rejects_invalid(gap_db):
    from app.services.knowledge_gap_service import knowledge_gap_service as svc
    with pytest.raises(ValueError):
        await svc.update_status(1, "u1", is_admin=True, status="not_a_status")
```

- [ ] **Step 2: 运行确认失败**

Run:
```bash
uv run pytest tests/test_knowledge_gap_service.py -v
```
Expected: FAIL，`ModuleNotFoundError: app.services.knowledge_gap_service`。

- [ ] **Step 3: 实现 service**

Create `backend/app/services/knowledge_gap_service.py`:
```python
"""知识缺口 service：落库（去重）/ 查询（按身份过滤）/ 改状态（越权防护）。仿 document_service。"""
import datetime
from typing import List, Dict, Any, Optional

from app.db.db_config import AsyncSessionLocal
from app.models.chat_history import KnowledgeGap
from app.core.logger_handler import logger

_VALID_STATUS = {"pending", "reviewed", "resolved", "ignored"}


class KnowledgeGapService:

    async def save_gap(
        self, user_id: str, dept_id: Optional[str], title: str,
        question: str, category: str, suggested_content: str,
    ) -> None:
        """去重：同 user_id + 相同 question + status='pending' 已存在则 touch updated_at；否则插入。"""
        async with AsyncSessionLocal() as db:
            existing = await db.run_sync(
                lambda s: s.query(KnowledgeGap)
                .filter(
                    KnowledgeGap.user_id == user_id,
                    KnowledgeGap.question == question,
                    KnowledgeGap.status == "pending",
                )
                .first()
            )
            if existing:
                existing.updated_at = datetime.datetime.now(datetime.timezone.utc)
                await db.commit()
                logger.info(f"[GapService] 去重命中，touch gap id={existing.id} user={user_id}")
                return
            gap = KnowledgeGap(
                user_id=user_id, dept_id=dept_id, title=title,
                question=question, category=category, suggested_content=suggested_content,
            )
            db.add(gap)
            await db.commit()
            logger.info(f"[GapService] 新增缺口 user={user_id} title={title}")

    async def list_gaps(
        self, user_id: str, is_admin: bool, status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        async with AsyncSessionLocal() as db:
            def _query(s):
                q = s.query(KnowledgeGap)
                if not is_admin:
                    q = q.filter(KnowledgeGap.user_id == user_id)
                if status:
                    q = q.filter(KnowledgeGap.status == status)
                return q.order_by(KnowledgeGap.updated_at.desc()).all()
            records = await db.run_sync(_query)
            return [self._to_dict(r) for r in records]

    async def update_status(
        self, gap_id: int, user_id: str, is_admin: bool, status: str
    ) -> bool:
        if status not in _VALID_STATUS:
            raise ValueError(f"非法状态: {status}")
        async with AsyncSessionLocal() as db:
            gap = await db.run_sync(
                lambda s: s.query(KnowledgeGap).filter(KnowledgeGap.id == gap_id).first()
            )
            if not gap:
                return False
            if not is_admin and gap.user_id != user_id:
                raise PermissionError("无权修改他人的知识缺口")
            gap.status = status
            await db.commit()
            return True

    @staticmethod
    def _to_dict(r: KnowledgeGap) -> Dict[str, Any]:
        return {
            "id": r.id,
            "user_id": r.user_id,
            "title": r.title,
            "question": r.question,
            "category": r.category,
            "suggested_content": r.suggested_content,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }


knowledge_gap_service = KnowledgeGapService()
```

- [ ] **Step 4: 运行确认通过**

Run:
```bash
uv run pytest tests/test_knowledge_gap_service.py -v
```
Expected: 5 个用例全 PASS。

- [ ] **Step 5: Commit**

```bash
git add app/services/knowledge_gap_service.py tests/test_knowledge_gap_service.py
git commit -m "feat: 新增 knowledge_gap_service（去重/过滤/越权防护）"
```

---

## Task 3: KnowledgeGap 节点

**Files:**
- Create: `backend/app/agent/graph/nodes/knowledge_gap.py`
- Test: `backend/tests/test_graph_knowledge_gap_node.py`

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_graph_knowledge_gap_node.py`:
```python
import pytest

from app.agent.graph.nodes.knowledge_gap import knowledge_gap_node, _parse_gap
from app.utils.auth_utils import RequestIdentity


def test_parse_gap_plain_json():
    text = '{"title": "设备报销", "category": "财务", "suggested_content": "1.哪些可报"}'
    gap = _parse_gap(text, fallback_question="远程设备损坏报销")
    assert gap["title"] == "设备报销" and gap["category"] == "财务"


def test_parse_gap_fallback_on_garbage():
    gap = _parse_gap("不是JSON", fallback_question="远程设备损坏报销")
    assert gap["title"]  # 非空
    assert gap["category"] == "unknown"
    assert gap["suggested_content"]


class _FakeMsg:
    def __init__(self, content):
        self.content = content


@pytest.mark.asyncio
async def test_knowledge_gap_node_saves_and_builds_messages(monkeypatch):
    saved = {}

    async def _fake_save(user_id, dept_id, title, question, category, suggested_content):
        saved.update(user_id=user_id, title=title, question=question)

    async def _fake_ainvoke(_messages):
        return _FakeMsg('{"title": "远程设备报销", "category": "财务", "suggested_content": "1.哪些设备 2.是否审批"}')

    import app.agent.graph.nodes.knowledge_gap as kg
    monkeypatch.setattr(kg.knowledge_gap_service, "save_gap", _fake_save)

    class _FakeModel:
        ainvoke = staticmethod(_fake_ainvoke)
    monkeypatch.setattr(kg, "chat_model", _FakeModel())

    state = {"query": "远程办公设备损坏怎么报销",
             "identity": RequestIdentity(user_id="u1", dept_id="d1")}
    update = await knowledge_gap_node(state)

    # 落库被调用，参数正确
    assert saved["user_id"] == "u1"
    assert saved["question"] == "远程办公设备损坏怎么报销"
    # 构造了 task_messages 供 finalize 流式告知
    assert update["task_messages"][0]["role"] == "system"
    assert update["trace"][0]["agent"] == "knowledge_gap"


@pytest.mark.asyncio
async def test_knowledge_gap_node_survives_save_failure(monkeypatch):
    async def _fake_save(**kwargs):
        raise RuntimeError("db down")

    async def _fake_ainvoke(_messages):
        return _FakeMsg('{"title":"t","category":"c","suggested_content":"s"}')

    import app.agent.graph.nodes.knowledge_gap as kg
    monkeypatch.setattr(kg.knowledge_gap_service, "save_gap", _fake_save)

    class _FakeModel:
        ainvoke = staticmethod(_fake_ainvoke)
    monkeypatch.setattr(kg, "chat_model", _FakeModel())

    state = {"query": "q", "identity": None}
    update = await knowledge_gap_node(state)
    # 落库失败不阻塞：仍返回 task_messages 告知用户
    assert "task_messages" in update
```

- [ ] **Step 2: 运行确认失败**

Run:
```bash
uv run pytest tests/test_graph_knowledge_gap_node.py -v
```
Expected: FAIL，`ModuleNotFoundError: app.agent.graph.nodes.knowledge_gap`。

- [ ] **Step 3: 实现节点**

Create `backend/app/agent/graph/nodes/knowledge_gap.py`:
```python
import json
import re

from app.agent.graph._stream import safe_get_stream_writer
from app.agent.graph.state import AgentState
from app.services.knowledge_gap_service import knowledge_gap_service
from app.core.logger_handler import logger
from app.utils.factory import chat_model

_GAP_PROMPT = """用户的问题在企业知识库中找不到明确依据。请基于这个问题，生成一条"待补充知识条目"，
只输出一个 JSON 对象，不要额外解释，格式：
{"title": "<简短标题>", "category": "<问题类型，如 财务报销/远程办公/人事>", "suggested_content": "<建议补充的内容，列出若干要点>"}"""


def _fallback_gap(fallback_question: str) -> dict:
    title = fallback_question[:50] if fallback_question else "未命名缺口"
    return {
        "title": title,
        "category": "unknown",
        "suggested_content": "建议补充该问题相关的制度依据与处理流程。",
    }


def _parse_gap(text: str, fallback_question: str) -> dict:
    if not text:
        return _fallback_gap(fallback_question)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return _fallback_gap(fallback_question)
    try:
        data = json.loads(match.group(0))
    except (json.JSONDecodeError, ValueError):
        return _fallback_gap(fallback_question)
    fb = _fallback_gap(fallback_question)
    return {
        "title": str(data.get("title") or fb["title"]),
        "category": str(data.get("category") or "unknown"),
        "suggested_content": str(data.get("suggested_content") or fb["suggested_content"]),
    }


def _build_notice_messages(query: str, gap: dict) -> list:
    system = (
        "你要如实告知用户：知识库中没有找到该问题的明确依据，系统已生成一条待补充知识条目。"
        "用简洁中文复述：缺口标题、问题类型、建议补充的内容要点。不要编造制度内容。"
    )
    user = (
        f"用户问题：{query}\n"
        f"缺口标题：{gap['title']}\n问题类型：{gap['category']}\n"
        f"建议补充内容：{gap['suggested_content']}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


async def knowledge_gap_node(state: AgentState) -> dict:
    """检索不足/缺口类问题：生成结构化缺口 → 落库（去重）→ 经 finalize 流式告知用户。"""
    query = state["query"]
    writer = safe_get_stream_writer()
    writer({"kind": "step", "id": "task_execute", "status": "running",
            "level": "info", "detail": "正在记录知识缺口", "title": "记录知识缺口"})

    # 1. LLM 生成结构化缺口
    msg = await chat_model.ainvoke(
        [{"role": "system", "content": _GAP_PROMPT},
         {"role": "user", "content": query}]
    )
    text = msg.content if hasattr(msg, "content") else str(msg)
    gap = _parse_gap(text, fallback_question=query)

    # 2. 落库（失败不阻塞）
    identity = state.get("identity")
    user_id = (identity.user_id if identity else "") or ""
    dept_id = identity.dept_id if identity else None
    save_status = "done"
    try:
        await knowledge_gap_service.save_gap(
            user_id=user_id, dept_id=dept_id, title=gap["title"],
            question=query, category=gap["category"],
            suggested_content=gap["suggested_content"],
        )
    except Exception as e:  # 落库失败降级，不影响告知用户
        save_status = "failed"
        logger.error(f"[KnowledgeGap] 落库失败: {e}", exc_info=True)

    writer({"kind": "step", "id": "task_execute", "status": "done",
            "level": "success", "detail": "已记录知识缺口", "title": "记录知识缺口"})

    # 3. 构造 finalize 流式告知 messages
    return {
        "task_messages": _build_notice_messages(query, gap),
        "trace": [{"agent": "knowledge_gap", "status": save_status,
                   "output": f"title={gap['title']} category={gap['category']}"}],
    }
```

- [ ] **Step 4: 运行确认通过**

Run:
```bash
uv run pytest tests/test_graph_knowledge_gap_node.py -v
```
Expected: 4 个用例全 PASS。

- [ ] **Step 5: Commit**

```bash
git add app/agent/graph/nodes/knowledge_gap.py tests/test_graph_knowledge_gap_node.py
git commit -m "feat: 新增 KnowledgeGap 节点（LLM 生成 + 落库 + task_messages）"
```

---

## Task 4: route_after_knowledge 扩展 + build.py 接入

**Files:**
- Modify: `backend/app/agent/graph/nodes/task.py`（扩展 `route_after_knowledge`）
- Modify: `backend/app/agent/graph/build.py`（接入 knowledge_gap 节点）
- Test: `backend/tests/test_graph_gap_routing.py`

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_graph_gap_routing.py`:
```python
import pytest

from app.agent.graph.nodes.task import route_after_knowledge


def test_route_to_gap_when_not_enough():
    state = {"plan": {"task_type": "knowledge_qa"}, "documents": [], "is_enough": False}
    assert route_after_knowledge(state) == "knowledge_gap"


def test_route_to_gap_when_coordinator_says_gap():
    state = {"plan": {"task_type": "knowledge_gap"}, "documents": ["d"], "is_enough": True}
    assert route_after_knowledge(state) == "knowledge_gap"


def test_gap_priority_over_task():
    # is_enough=False 时即使是任务类型也走缺口（不强行生成）
    state = {"plan": {"task_type": "document_compare"}, "documents": [], "is_enough": False}
    assert route_after_knowledge(state) == "knowledge_gap"


def test_route_to_task_still_works():
    state = {"plan": {"task_type": "document_compare"}, "documents": ["d"], "is_enough": True}
    assert route_after_knowledge(state) == "task"


def test_route_to_finalize_for_plain_qa():
    state = {"plan": {"task_type": "knowledge_qa"}, "documents": ["d"], "is_enough": True}
    assert route_after_knowledge(state) == "finalize"


@pytest.mark.asyncio
async def test_graph_routes_through_gap_node_when_no_docs(monkeypatch):
    """is_enough=False（无文档）：图应经过 knowledge_gap 节点，落库被调用。"""
    import app.agent.graph.nodes.coordinator as co
    import app.agent.graph.nodes.knowledge as kn
    import app.agent.graph.nodes.finalize as fz
    import app.agent.graph.nodes.knowledge_gap as kg

    class _Msg:
        def __init__(self, c):
            self.content = c

    async def _fake_coord(_m):
        return _Msg('{"task_type": "knowledge_qa", "need_retrieval": true, "reason": "x"}')

    async def _fake_get_docs(query, filter_meta=None):
        return {"documents": [], "citations": [], "summary": "", "error": None}  # 无文档→is_enough=False

    async def _fake_gap_invoke(_m):
        return _Msg('{"title":"缺口","category":"c","suggested_content":"s"}')

    async def _fake_final(_m):
        return _Msg("知识库暂无依据，已记录缺口。")

    saved = {"hit": False}

    async def _fake_save(**kwargs):
        saved["hit"] = True

    monkeypatch.setattr(co, "chat_model", type("M", (), {"ainvoke": staticmethod(_fake_coord)})())
    monkeypatch.setattr(kn.rag_service, "get_documents_for_agent", _fake_get_docs)
    monkeypatch.setattr(kg, "chat_model", type("M", (), {"ainvoke": staticmethod(_fake_gap_invoke)})())
    monkeypatch.setattr(kg.knowledge_gap_service, "save_gap", _fake_save)
    monkeypatch.setattr(fz, "chat_model", type("M", (), {"ainvoke": staticmethod(_fake_final)})())

    from app.agent.graph.build import build_graph
    graph = build_graph()
    result = await graph.ainvoke({"query": "远程设备报销", "history": [], "trace": []})

    assert saved["hit"] is True   # 缺口落库被触发
    assert result["final_answer"] == "知识库暂无依据，已记录缺口。"
```

- [ ] **Step 2: 运行确认失败**

Run:
```bash
uv run pytest tests/test_graph_gap_routing.py -v
```
Expected: 路由单测 FAIL（`route_after_knowledge` 还没有缺口分支，`is_enough=False` 当前会落到 finalize）；集成测试 FAIL（图无 knowledge_gap 节点）。

- [ ] **Step 3: 扩展 route_after_knowledge**

修改 `backend/app/agent/graph/nodes/task.py` 的 `route_after_knowledge` 为：
```python
def route_after_knowledge(state: AgentState) -> str:
    """knowledge 之后的路由。缺口判断优先于 task（无依据不强行生成）。"""
    plan = state.get("plan") or {}
    if not state.get("is_enough", True) or plan.get("task_type") == "knowledge_gap":
        return "knowledge_gap"
    if plan.get("task_type") in TASK_TYPES_NEEDING_TASK and state.get("documents"):
        return "task"
    return "finalize"
```
（`TASK_TYPES_NEEDING_TASK` 已在本文件定义，不变。）

- [ ] **Step 4: 改 build.py 接入 knowledge_gap 节点**

修改 `backend/app/agent/graph/build.py` 为：
```python
from langgraph.graph import StateGraph, START, END

from app.agent.graph.state import AgentState
from app.agent.graph.nodes.coordinator import coordinator_node, route_after_coordinator
from app.agent.graph.nodes.knowledge import knowledge_node
from app.agent.graph.nodes.task import task_node, route_after_knowledge
from app.agent.graph.nodes.knowledge_gap import knowledge_gap_node
from app.agent.graph.nodes.finalize import finalize_node


def build_graph():
    """Phase 5a 图：
    START → coordinator →(条件)→ knowledge|finalize
    knowledge →(条件)→ knowledge_gap|task|finalize
    knowledge_gap → finalize；task → finalize；finalize → END
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

- [ ] **Step 5: 运行确认通过**

Run:
```bash
uv run pytest tests/test_graph_gap_routing.py -v
```
Expected: 全部 PASS（5 路由单测 + 1 集成测试）。

- [ ] **Step 6: 行尾核查 + Commit**

```bash
git diff --stat app/agent/graph/nodes/task.py app/agent/graph/build.py
git diff --stat --ignore-all-space app/agent/graph/nodes/task.py app/agent/graph/build.py
```
（两文件均 Phase 3/4 新建，通常 LF；若差距大用 PowerShell 转回。）
```bash
git add app/agent/graph/nodes/task.py app/agent/graph/build.py tests/test_graph_gap_routing.py
git commit -m "feat: 图接入 KnowledgeGap 节点，缺口路由优先于 task"
```

---

## Task 5: 缺口 CRUD API

**Files:**
- Modify: `backend/app/router/chat.py`（新增两个 endpoint）
- Test: `backend/tests/test_knowledge_gap_api.py`

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_knowledge_gap_api.py`:
```python
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.models.chat_history import Base
from app.utils.auth_utils import RequestIdentity


@pytest_asyncio.fixture
async def api_client(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    import app.services.knowledge_gap_service as mod
    monkeypatch.setattr(mod, "AsyncSessionLocal", Session)

    from main import app
    from app.utils.auth_utils import get_current_identity
    app.dependency_overrides[get_current_identity] = lambda: RequestIdentity(user_id="u1", is_admin=False)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 预置一条缺口
        from app.services.knowledge_gap_service import knowledge_gap_service as svc
        await svc.save_gap("u1", None, "T", "问题Q", "c", "s")
        yield client

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_list_gaps_api(api_client):
    resp = await api_client.get("/api/knowledge-gaps")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 1 and data["gaps"][0]["title"] == "T"


@pytest.mark.asyncio
async def test_patch_status_api(api_client):
    gid = (await api_client.get("/api/knowledge-gaps")).json()["data"]["gaps"][0]["id"]
    resp = await api_client.patch(f"/api/knowledge-gaps/{gid}", json={"status": "resolved"})
    assert resp.status_code == 200
    again = await api_client.get("/api/knowledge-gaps?status=resolved")
    assert again.json()["data"]["total"] == 1
```

> 注：`main` 模块导入 app 时会触发图编译与各 service 初始化；测试环境已装好依赖与 .env，导入应正常。若 `httpx` 未安装，先 `uv add --dev httpx`（它通常随 fastapi 测试已存在；运行 Step 2 时若报缺失再装）。

- [ ] **Step 2: 运行确认失败**

Run:
```bash
uv run pytest tests/test_knowledge_gap_api.py -v
```
Expected: FAIL（`/api/knowledge-gaps` 路由不存在 → 404，断言失败）。若报 `ModuleNotFoundError: httpx`，先 `uv add --dev httpx` 再重跑。

- [ ] **Step 3: 在 chat.py 新增两个 endpoint**

在 `backend/app/router/chat.py` 末尾（其它 `@chat_router` 路由附近）新增：
```python
@chat_router.get("/knowledge-gaps")
async def list_knowledge_gaps(
    status: str = Query(None, description="按状态筛选：pending/reviewed/resolved/ignored"),
    identity: RequestIdentity = Depends(get_current_identity),
):
    """列出知识缺口（管理员看全部，普通用户看自己产生的）"""
    from app.services.knowledge_gap_service import knowledge_gap_service
    gaps = await knowledge_gap_service.list_gaps(
        identity.user_id, is_admin=identity.is_admin, status=status
    )
    return success_response(data={"gaps": gaps, "total": len(gaps)})


@chat_router.patch("/knowledge-gaps/{gap_id}")
async def update_knowledge_gap(
    gap_id: int,
    body: dict = Body(...),
    identity: RequestIdentity = Depends(get_current_identity),
):
    """修改知识缺口状态（非管理员只能改自己的）"""
    from app.services.knowledge_gap_service import knowledge_gap_service
    status = body.get("status")
    try:
        ok = await knowledge_gap_service.update_status(
            gap_id, identity.user_id, is_admin=identity.is_admin, status=status
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="知识缺口不存在")
    return success_response(message="状态已更新")
```
（`Query`、`Body`、`Depends`、`HTTPException`、`get_current_identity`、`RequestIdentity`、`success_response` 在 chat.py 顶部均已 import，直接用。）

- [ ] **Step 4: 运行确认通过**

Run:
```bash
uv run pytest tests/test_knowledge_gap_api.py -v
```
Expected: 2 个用例全 PASS。

- [ ] **Step 5: 行尾核查 + Commit**

```bash
git diff --stat app/router/chat.py
git diff --stat --ignore-all-space app/router/chat.py
```
（chat.py 是既有 CRLF 文件，务必核查；差距大用 PowerShell 转回 CRLF。）
```bash
git add app/router/chat.py tests/test_knowledge_gap_api.py
git commit -m "feat: 新增知识缺口查询/改状态 API"
```

---

## Task 6: 全量回归 + 端到端验证

**Files:** 无（验证任务）

- [ ] **Step 1: 全量回归**

Run:
```bash
uv run pytest tests/ -q
```
Expected: 全部 PASS（既有契约测试 + Phase 1-4 全部 graph 测试 + 本 Phase 新增 service/节点/路由/API 测试）。任何失败原样贴报告。

- [ ] **Step 2: 端到端真实验证（controller 执行，非 subagent）**

> 控制者用临时脚本真实运行后删除。验证一个明显超出知识库范围的问题触发缺口路径、落库、finalize 告知。subagent 实现到 Step 1 即可。

临时脚本 `backend/_tmp_phase5a_verify.py`（验证后删除）：
```python
import asyncio
from app.agent.graph.runner import graph_runner
from app.services.knowledge_gap_service import knowledge_gap_service


async def main():
    q = "在火星办公室加班的餐补标准是多少"   # 知识库几乎不可能有
    events = []
    async for e in graph_runner.stream(q, history=[], identity=None):
        events.append(e)
    step_ids = [e["data"].get("id") for e in events if e["type"] == "agent_step_update"]
    tokens = "".join(e["data"] for e in events if e["type"] == "token")
    print("step ids:", step_ids)
    print("出现记录知识缺口:", "task_execute" in step_ids)
    print("回答前120字:", tokens[:120])
    gaps = await knowledge_gap_service.list_gaps("", is_admin=True)
    print("缺口表记录数:", len(gaps))
    if gaps:
        print("最新缺口:", gaps[0]["title"], "|", gaps[0]["category"])


if __name__ == "__main__":
    asyncio.run(main())
```
运行：`PYTHONPATH=<backend绝对路径> uv run python _tmp_phase5a_verify.py`
预期：出现 `task_execute`（记录知识缺口）步骤；回答如实说明无依据并复述待补充条目；缺口表新增记录（真实落库，注意此脚本会向真实 MySQL 写入一条缺口，验证后可在 DB 手动清理）。token 干净。验证后删除临时脚本。

> ⚠️ 该 e2e 会向真实数据库写入一条缺口记录（user_id 为空串）。controller 验证后提示用户该测试数据可按需清理。

- [ ] **Step 3: 记录结论**

记录 `Phase 5a 通过 / 问题`。通过即可合并到 master，并着手 5b（前端缺口页）。

---

## 后续

- **5b：** 前端知识缺口列表页（Vue3，调本计划的 GET/PATCH API），另开计划。
- **Phase 6：** `agent_traces` 落库。
- **Phase 7：** 默认引擎切 graph。
