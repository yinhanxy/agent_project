from typing import List, Dict, Any
import os
from dotenv import load_dotenv
from app.core.logger_handler import logger

load_dotenv()

RERANKER_TYPE = os.getenv("RERANKER_TYPE", "LOCAL").upper()


# ── 本地 CrossEncoder（RERANKER_TYPE=LOCAL）────────────────────────────────────

def find_model_path(base_path: str) -> str:
    if os.path.exists(os.path.join(base_path, 'config.json')):
        return base_path
    for root, dirs, files in os.walk(base_path):
        if 'config.json' in files:
            return root
    return base_path


def check_and_download_reranker_model() -> None:
    """启动时检查本地重排序模型（仅 LOCAL 模式执行）"""
    if RERANKER_TYPE != "LOCAL":
        logger.info(f"[Reranker] 使用 {RERANKER_TYPE} 模式，跳过本地模型检查")
        return

    from modelscope import snapshot_download
    from tqdm import tqdm

    LOCAL_MODEL_PATH = os.getenv("RERANKER_MODEL_PATH", r"D:\Hugging_Face\models\Qwen3-Reranker-0.6B")
    MODELSCOPE_MODEL_NAME = "Qwen/Qwen3-Reranker-0.6B"

    try:
        if os.path.exists(LOCAL_MODEL_PATH) and os.path.isdir(LOCAL_MODEL_PATH):
            logger.info(f"✅ 检测到本地重排序模型：{LOCAL_MODEL_PATH}")
        else:
            logger.warning(f"⚠️  本地模型未找到：{LOCAL_MODEL_PATH}")
            logger.info(f"🔄 开始从魔搭社区下载模型：{MODELSCOPE_MODEL_NAME}")
            os.makedirs(LOCAL_MODEL_PATH, exist_ok=True)
            with tqdm(total=100, desc='下载模型', leave=True) as pbar:
                pbar.update(10)
                snapshot_download(model_id=MODELSCOPE_MODEL_NAME, cache_dir=LOCAL_MODEL_PATH, revision='master')
                pbar.update(90)
            logger.info(f"✅ 模型下载完成，保存路径：{LOCAL_MODEL_PATH}")
    except Exception as e:
        logger.error(f"❌ 模型检查失败: {str(e)}")
        raise RuntimeError(f"重排序模型检查失败: {str(e)}")


# ── 阿里云 DashScope Reranker（RERANKER_TYPE=ALIYUN）─────────────────────────

class _AliyunReranker:
    def __init__(self):
        import dashscope
        self._ds = dashscope
        self._ds.api_key = os.getenv("ALIYUN_RERANKER_API_KEY") or os.getenv("ALIYUN_ACCESS_KEY_SECRET")
        self.model_name = os.getenv("ALIYUN_RERANKER_MODEL_NAME", "qwen3-vl-rerank")
        logger.info(f"📦 Reranker 使用阿里云模型: {self.model_name}")

    def rerank(self, query: str, documents: List[str]) -> List[float]:
        resp = self._ds.TextReRank.call(
            model=self.model_name,
            query=query,
            documents=documents,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"阿里云 Reranker 调用失败: {resp.message}")
        results = resp.output.get("results", [])
        scores = [0.0] * len(documents)
        for item in results:
            scores[item["index"]] = item["relevance_score"]
        return scores


# ── ReorderService ─────────────────────────────────────────────────────────────

class ReorderService:

    def __init__(self):
        self._local_model = None
        self._aliyun = None

    async def _get_scorer(self):
        if RERANKER_TYPE == "ALIYUN":
            if self._aliyun is None:
                self._aliyun = _AliyunReranker()
            return "aliyun", self._aliyun
        else:
            import torch
            from sentence_transformers import CrossEncoder
            if self._local_model is None:
                path = find_model_path(os.getenv("RERANKER_MODEL_PATH", r"D:\Hugging_Face\models\Qwen3-Reranker-0.6B"))
                device = "cuda" if torch.cuda.is_available() else "cpu"
                logger.info(f"✅ 加载本地重排序模型：{path}")
                m = CrossEncoder(path, max_length=512, device=device, local_files_only=True)
                m.eval()
                self._local_model = m
            return "local", self._local_model

    async def reorder_documents(self, query: str, documents: List[str]) -> Dict[str, Any]:
        try:
            if not documents:
                return {"success": True, "documents": [], "error": ""}

            scorer_type, scorer = await self._get_scorer()

            if scorer_type == "aliyun":
                scores = scorer.rerank(query, documents)
            else:
                import torch
                pairs = [(query, doc) for doc in documents]
                with torch.no_grad():
                    scores = scorer.predict(pairs, batch_size=1)

            scored = [
                {"document": doc, "similarity": float(score)}
                for doc, score in zip(documents, scores)
            ]
            sorted_docs = sorted(scored, key=lambda x: x["similarity"], reverse=True)
            logger.info(f"[Reranker] 重排序完成，{len(sorted_docs)} 个文档，模式={scorer_type}")
            return {"success": True, "documents": sorted_docs, "error": ""}

        except Exception as e:
            logger.error(f"[Reranker] 重排序失败: {e}")
            return {"success": False, "documents": [], "error": str(e)}

    @staticmethod
    async def format_reorder_result(sorted_docs: List[Dict]) -> str:
        result = "重排序后的文档列表：\n"
        for i, doc in enumerate(sorted_docs, 1):
            result += f"{i}. 相似度: {doc.get('similarity', 0):.4f}\n"
            result += f"   内容: {doc.get('document', '')}\n\n"
        return result


reorder_service = ReorderService()
