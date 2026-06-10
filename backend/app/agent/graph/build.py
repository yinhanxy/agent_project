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
