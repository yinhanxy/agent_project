from langgraph.graph import StateGraph, START, END

from app.agent.graph.state import AgentState
from app.agent.graph.nodes.finalize import finalize_node


def build_graph():
    """Phase 1 最小图：START -> finalize -> END。

    后续 Phase 在此基础上加 knowledge / coordinator / task 节点与条件边。
    """
    g = StateGraph(AgentState)
    g.add_node("finalize", finalize_node)
    g.add_edge(START, "finalize")
    g.add_edge("finalize", END)
    return g.compile()
