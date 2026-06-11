"""Critic 回路的配置开关（env 驱动）。

独立成模块：build.py / task.py / critic.py 都要读它，
放这里避免 task ↔ critic 互相 import 形成循环。
"""
import os


def critic_enabled() -> bool:
    """critic 节点总开关；false/0/no 关闭后退化回现行单向流水线（紧急回退用）。"""
    return os.getenv("AGENT_CRITIC_ENABLE", "true").strip().lower() not in ("false", "0", "no")


def critic_max_revisions() -> int:
    """critic 触发改写重做的上限（默认 1，即最多改写一次）。

    设硬上限 _MAX_ALLOWED 防止极端配置：每次重做约加 2 个图节点步，
    取值过大会逼近 LangGraph 默认 recursion_limit=25 触发 GraphRecursionError。
    """
    _MAX_ALLOWED = 5
    try:
        return min(_MAX_ALLOWED, max(0, int(os.getenv("AGENT_CRITIC_MAX_REVISIONS", "1"))))
    except ValueError:
        return 1
