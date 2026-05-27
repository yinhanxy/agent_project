"""
Agent 生命周期钩子 —— 纯日志，无框架依赖。
AgentLoop 在关键节点调用这些函数。
"""
from app.core.logger_handler import logger


def on_agent_start(messages: list):
    logger.info(f"[Agent] 启动，消息数: {len(messages)}")


def on_agent_end(response: str, steps: list):
    logger.info(f"[Agent] 结束，工具调用次数: {len(steps)}，响应长度: {len(response)}")


def on_tool_call(name: str, arguments: str):
    logger.info(f"[Tool] 调用 {name}，参数: {arguments}")


def on_tool_result(name: str, result: str):
    logger.info(f"[Tool] {name} 返回: {result[:300]}")


def on_model_call(messages: list):
    logger.info(f"[LLM] 调用模型，消息数: {len(messages)}")


def on_model_response(has_tool_calls: bool, content_len: int):
    logger.info(f"[LLM] 响应，包含工具调用: {has_tool_calls}，内容长度: {content_len}")
