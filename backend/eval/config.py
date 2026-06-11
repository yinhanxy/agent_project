from dataclasses import dataclass


@dataclass(frozen=True)
class EvalConfig:
    name: str
    env: dict          # 该配置要注入的环境变量（覆盖在当前 env 之上）


# P0 消融矩阵：在 graph 引擎下，逐个打开 critic / hyde 与 baseline 对照。
# 每个配置都显式写全三个开关，避免继承上一配置的残留。
_GRAPH = {"AGENT_ENGINE": "graph"}

CONFIG_MATRIX = [
    EvalConfig("baseline", {**_GRAPH, "AGENT_CRITIC_ENABLE": "false", "RAG_HYDE_ENABLE": "false"}),
    EvalConfig("+critic",  {**_GRAPH, "AGENT_CRITIC_ENABLE": "true",  "RAG_HYDE_ENABLE": "false"}),
    EvalConfig("+hyde",    {**_GRAPH, "AGENT_CRITIC_ENABLE": "false", "RAG_HYDE_ENABLE": "true"}),
]
