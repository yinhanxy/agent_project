from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Optional, List
import os
from dotenv import load_dotenv

from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_ollama import OllamaEmbeddings, ChatOllama

from app.core.logger_handler import logger

# 加载环境变量
load_dotenv()

_DEEPSEEK_ROLE_ENV = {
    "coordinator": ("DEEPSEEK_MODEL_COORDINATOR", "deepseek-v4-flash"),
    "knowledge_gap": ("DEEPSEEK_MODEL_COORDINATOR", "deepseek-v4-flash"),
    "finalize": ("DEEPSEEK_MODEL_FINALIZE", "deepseek-v4-pro"),
    # RAG 摘要 / HyDE 等内部轻量任务，用便宜快的 flash
    "rag": ("DEEPSEEK_MODEL_RAG", "deepseek-v4-flash"),
}


class DashScopeEmbeddingsWrapper(Embeddings):
    """阿里云DashScope嵌入模型封装"""
    
    def __init__(self, model_name: str = "qwen3-embedding", api_key: str = None):
        try:
            import dashscope
            self.dashscope = dashscope
            self.dashscope.api_key = api_key or os.getenv("ALIYUN_ACCESS_KEY_SECRET")
            self.model_name = model_name
        except ImportError:
            raise ImportError("需要安装 dashscope 库: pip install dashscope")
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量嵌入文档（每批最多 25 条，减少 API 调用次数）"""
        BATCH_SIZE = 10
        results: List[List[float]] = [[] for _ in texts]
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i:i + BATCH_SIZE]
            resp = self.dashscope.TextEmbedding.call(
                model=self.model_name,
                input=batch,
            )
            if resp.status_code == 200:
                for item in resp.output["embeddings"]:
                    results[i + item["text_index"]] = item["embedding"]
            else:
                raise RuntimeError(f"阿里云嵌入调用失败（模型: {self.model_name}）: {resp.message}")
        return results
    
    def embed_query(self, text: str) -> List[float]:
        """嵌入单个查询"""
        resp = self.dashscope.TextEmbedding.call(
            model=self.model_name,
            input=text
        )
        if resp.status_code != 200:
            raise RuntimeError(f"阿里云嵌入调用失败（模型: {self.model_name}）: {resp.message}")
        # DashScope 响应统一格式：{"embeddings": [{"embedding": [...], "text_index": 0}]}
        embeddings = resp.output.get("embeddings") or []
        if not embeddings:
            raise RuntimeError(f"阿里云嵌入响应为空（模型: {self.model_name}）")
        return embeddings[0]["embedding"]


class BaseModelFactory(ABC):
    """基础模型工厂"""

    @abstractmethod
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        """生成模型"""
        pass


def _build_deepseek_chat_model(role: str) -> BaseChatModel:
    from langchain_deepseek import ChatDeepSeek

    env_key, default_model = _DEEPSEEK_ROLE_ENV.get(role, _DEEPSEEK_ROLE_ENV["finalize"])
    model_name = os.getenv(env_key, default_model)
    logger.info(f"📦 ChatModel 使用DeepSeek模型: role={role}, model={model_name}")
    return ChatDeepSeek(
        model=model_name,
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        streaming=True,
        top_p=0.7,
        extra_body={"thinking": {"type": "disabled"}},
    )


class ChatModelFactory(BaseModelFactory):
    """聊天模型工厂 - 支持阿里云百炼、Ollama 和 DeepSeek"""
    
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        """根据LLM_TYPE生成对应的聊天模型"""
        llm_type = os.getenv("LLM_TYPE", "ALIYUN").upper()
        
        if llm_type == "OLLAMA":
            model_name = os.getenv("OLLAMA_MODEL_NAME", os.getenv("OLLAMA_CHAT_MODEL_NAME", "qwen3:7b"))
            base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            
            logger.info(f"📦 ChatModel 使用Ollama模型: {model_name}, 地址: {base_url}")
            
            return ChatOllama(
                model=model_name,
                base_url=base_url,
                streaming=True,
                top_p=0.7,
            )
        
        elif llm_type == "ALIYUN":
            model_name = os.getenv("ALIYUN_MODEL_NAME", os.getenv("CHAT_MODEL_NAME", "qwen3-max"))
            api_key = os.getenv("ALIYUN_ACCESS_KEY_SECRET")
            base_url = os.getenv("ALIYUN_BASE_URL")
            
            logger.info(f"📦 ChatModel 使用阿里云百炼模型: {model_name}")
            
            return ChatTongyi(
                model=model_name,
                api_key=api_key,
                base_url=base_url,
                streaming=True,
                top_p=0.7,
            )

        elif llm_type == "DEEPSEEK":
            return _build_deepseek_chat_model("finalize")
        
        else:
            raise ValueError(f"不支持的LLM_TYPE: {llm_type}，可选值: ALIYUN, OLLAMA, DEEPSEEK")


class EmbedModelFactory(BaseModelFactory):
    """嵌入模型工厂 - 支持Ollama和阿里云百炼"""
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        """根据EMBED_MODEL_TYPE生成对应的嵌入模型"""
        embed_type = os.getenv("EMBED_MODEL_TYPE", "OLLAMA").upper()
        
        if embed_type == "OLLAMA":
            model_name = os.getenv("TEXT_EMBEDDING_MODEL_NAME", "qwen3-embedding:0.6b")
            base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            
            logger.info(f"📦 EmbedModel 使用Ollama嵌入模型: {model_name}, 地址: {base_url}")
            
            return OllamaEmbeddings(
                model=model_name,
                base_url=base_url
            )
        
        elif embed_type == "ALIYUN":
            model_name = os.getenv("ALIYUN_EMBED_MODEL_NAME", "qwen3-embedding")
            api_key = os.getenv("ALIYUN_EMBED_API_KEY") or os.getenv("ALIYUN_ACCESS_KEY_SECRET")

            logger.info(f"📦 EmbedModel 使用阿里云嵌入模型: {model_name}")

            return DashScopeEmbeddingsWrapper(
                model_name=model_name,
                api_key=api_key
            )
        
        else:
            raise ValueError(f"不支持的EMBED_MODEL_TYPE: {embed_type}，可选值: OLLAMA, ALIYUN")


class RerankerModelFactory(BaseModelFactory):
    """重排序模型工厂 - 已废弃，使用CrossEncoder模型"""
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        """生成模型"""
        return None


chat_model = ChatModelFactory().generator()
embed_model = EmbedModelFactory().generator()
reranker_model = None


@lru_cache(maxsize=None)
def get_chat_model(role: str = "finalize") -> BaseChatModel:
    """按节点角色取 chat 模型；非 DeepSeek 保持原有单模型行为。"""
    llm_type = os.getenv("LLM_TYPE", "ALIYUN").upper()
    if llm_type != "DEEPSEEK":
        return chat_model
    normalized_role = role if role in _DEEPSEEK_ROLE_ENV else "finalize"
    return _build_deepseek_chat_model(normalized_role)
