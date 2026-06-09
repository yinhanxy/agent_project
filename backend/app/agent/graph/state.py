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

    # token 计量（各节点 append 本次 LLM 调用的 total，reducer 累加）
    token_usage: Annotated[int, operator.add]

    # 轨迹（append-only）
    trace: Annotated[list, operator.add]
