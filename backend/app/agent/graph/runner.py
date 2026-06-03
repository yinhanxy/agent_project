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
