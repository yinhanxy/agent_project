from eval.config import EvalConfig, CONFIG_MATRIX


def test_matrix_has_three_p0_configs():
    names = [c.name for c in CONFIG_MATRIX]
    assert names == ["baseline", "+critic", "+hyde"]


def test_all_configs_use_graph_engine():
    assert all(c.env.get("AGENT_ENGINE") == "graph" for c in CONFIG_MATRIX)


def test_baseline_disables_critic_and_hyde():
    base = next(c for c in CONFIG_MATRIX if c.name == "baseline")
    assert base.env["AGENT_CRITIC_ENABLE"] == "false"
    assert base.env["RAG_HYDE_ENABLE"] == "false"


def test_critic_config_enables_only_critic():
    c = next(c for c in CONFIG_MATRIX if c.name == "+critic")
    assert c.env["AGENT_CRITIC_ENABLE"] == "true"
    assert c.env["RAG_HYDE_ENABLE"] == "false"


def test_hyde_config_enables_only_hyde():
    c = next(c for c in CONFIG_MATRIX if c.name == "+hyde")
    assert c.env["RAG_HYDE_ENABLE"] == "true"
    assert c.env["AGENT_CRITIC_ENABLE"] == "false"
