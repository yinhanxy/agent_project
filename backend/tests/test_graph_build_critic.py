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
