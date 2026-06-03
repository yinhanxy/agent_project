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
