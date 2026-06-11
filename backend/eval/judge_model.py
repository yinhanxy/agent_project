"""LLM-judge 模型：独立用阿里云千问 qwen3-max（与被测 DeepSeek 不同家族，规避自评偏袒）。"""
import os
from langchain_community.chat_models.tongyi import ChatTongyi


def judge_model_name() -> str:
    return os.getenv("EVAL_JUDGE_MODEL", "qwen3-max")


def build_judge_model():
    """构造 judge 模型；temperature=0 降波动。"""
    return ChatTongyi(
        model=judge_model_name(),
        api_key=os.getenv("ALIYUN_JUDGE_API_KEY") or os.getenv("ALIYUN_ACCESS_KEY_SECRET"),
        base_url=os.getenv("ALIYUN_BASE_URL"),
        temperature=0,
    )
