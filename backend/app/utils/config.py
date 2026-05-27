import os

from app.utils.config_handler import load_config
from app.utils.path_tool import get_abstract_path

chroma_config = load_config(config_path=get_abstract_path('app/config/chroma.yaml'))
prompt_config = load_config(config_path=get_abstract_path('app/config/prompt.yaml'))
agent_config = load_config(config_path=get_abstract_path('app/config/agent.yaml'))

milvus_config = load_config(config_path=get_abstract_path('app/config/milvus.yaml'))
# env 覆盖 yaml 默认值
milvus_config["host"] = os.getenv("MILVUS_HOST", milvus_config.get("host", "localhost"))
milvus_config["port"] = int(os.getenv("MILVUS_PORT", milvus_config.get("port", 19530)))

if __name__ == '__main__':
    print(chroma_config)
    print(prompt_config)
    print(agent_config)
    print(milvus_config)