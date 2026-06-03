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
