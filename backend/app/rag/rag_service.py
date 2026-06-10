import asyncio
import os
import time
from typing import Optional, List, Dict, Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.documents import Document
from langsmith import traceable

from app.rag.vector_store import VectorStoreService
from app.rag.reorder_service import reorder_service
from app.services.parent_chunk_service import parent_chunk_service
from app.utils.factory import get_chat_model
from app.utils.prompt_loader import load_prompt
from app.core.logger_handler import logger

# 置信度阈值：普通 RAG 聊天（get_documents_and_summary）拒答用。
# 注意单位：本地 CrossEncoder 输出 logit（默认 -5.0 即为此设计）；阿里云 reranker 输出
# 0~1 的 relevance_score，此时 -5.0 永不命中、等于关闭拒答。两种 reranker 需配不同的值。
_CONFIDENCE_THRESHOLD = float(os.getenv("RAG_CONFIDENCE_THRESHOLD", "-5.0"))

# 知识缺口阈值：Agent 路径（get_documents_for_agent）专用，与上面的拒答阈值解耦。
# 语义按阿里云 0~1 的 relevance_score：最高分低于此值视为"知识库无明确依据"，
# 由 LangGraph 路由走 knowledge_gap 记录缺口。定标依据（全库样本）：
#   正常命中 0.816~0.932 / 相关越界 0.507~0.705 / 完全无关 0.413~0.472，
#   取空档 0.705~0.816 内的 0.75，正常命中留约 0.066 裕量。
_GAP_THRESHOLD = float(os.getenv("RAG_GAP_THRESHOLD", "0.75"))


class RetrievalError(RuntimeError):
    """检索系统故障（向量库/BM25/嵌入模型不可用等）。
    与"检索成功但无命中"是两类不同的失败：前者属于系统错误，
    应让上游明确感知；后者只是知识库内容不覆盖该问题。
    """


class RagService:
    def __init__(self):
        self.vector_store = VectorStoreService()
        self.retriever = None
        self._retriever_lock = asyncio.Lock()
        self.prompt_text = load_prompt(prompt_type="rag_summary_prompt")
        self.prompt_template = PromptTemplate.from_template(self.prompt_text)
        self.chat_model = get_chat_model("rag")
        self.chain = self._init_chain()
        self.hyde_prompt_template = PromptTemplate.from_template(
            "基于以下问题，生成一个详细的假设性回答，我会根据你的这个假设性回答在向量数据库里检索文档：\n\n问题：{query}\n\n假设性回答："
        )

    # ── 检索器管理 ────────────────────────────────────────────────────────────

    async def initialize_retriever(self, query: str = None):
        if self.retriever is None:
            async with self._retriever_lock:
                if self.retriever is None:
                    self.retriever = await self.vector_store.get_retriever(query)

    def invalidate_retriever(self):
        """文档变更后调用，下次请求时触发 BM25 重建"""
        self.retriever = None
        logger.info("【RAG】检索器已失效，下次请求将重建 BM25 索引")

    def _init_chain(self):
        return self.prompt_template | self.chat_model | StrOutputParser()

    # ── HyDE ──────────────────────────────────────────────────────────────────

    @traceable
    async def generate_hypothetical_document(self, query: str) -> str:
        t0 = time.perf_counter()
        try:
            hyde_chain = self.hyde_prompt_template | self.chat_model | StrOutputParser()
            hypothetical_doc = await hyde_chain.ainvoke({"query": query})
            logger.info(f"【HyDE】生成的假设性文档:\n{hypothetical_doc}")
            return hypothetical_doc
        except Exception as e:
            logger.error(f"【HyDE】生成假设性文档失败: {e}")
            return query
        finally:
            logger.info(
                f"[Timing][RAG] stage=hyde_generate "
                f"duration={time.perf_counter() - t0:.3f}s"
            )

    # ── 检索 ──────────────────────────────────────────────────────────────────

    @traceable
    async def retrieve_document(
        self, query: str, filter_meta: Optional[dict] = None
    ) -> List[Document]:
        """
        HyDE + 父子扩展检索。

        filter_meta: 若指定则每次构建带过滤的新检索器（KB 隔离）；
                     否则使用全局缓存检索器（个人文档 / agent 工具调用）。

        Raises:
            RetrievalError: 检索系统本身故障（向量库/BM25/嵌入模型异常）。
                "检索成功但 0 命中"不视为错误，返回 []。
        """
        try:
            init_t0 = time.perf_counter()
            if filter_meta:
                retriever = await self.vector_store.get_retriever(query, filter_meta=filter_meta)
            else:
                if self.retriever is None:
                    await self.initialize_retriever(query)
                retriever = self.retriever
            logger.info(
                f"[Timing][RAG] stage=retriever_init filtered={bool(filter_meta)} "
                f"duration={time.perf_counter() - init_t0:.3f}s"
            )
        except Exception as e:
            logger.error(f"【HyDE】检索器初始化失败: {e}", exc_info=True)
            raise RetrievalError(f"检索器初始化失败: {e}") from e

        total_t0 = time.perf_counter()
        logger.info(f"【HyDE】开始处理查询: {query}")
        hypothetical_doc = await self.generate_hypothetical_document(query)

        try:
            retrieve_t0 = time.perf_counter()
            child_docs = await retriever.ainvoke(hypothetical_doc)
            logger.info(
                f"[Timing][RAG] stage=child_retrieve child_count={len(child_docs)} "
                f"duration={time.perf_counter() - retrieve_t0:.3f}s"
            )
        except Exception as e:
            logger.error(f"【HyDE】向量/BM25 检索失败: {e}", exc_info=True)
            raise RetrievalError(f"向量/BM25 检索失败: {e}") from e

        logger.info(f"【HyDE】检索到 {len(child_docs)} 个子块")

        parent_ids = list({
            d.metadata["parent_id"]
            for d in child_docs
            if d.metadata.get("parent_id")
        })

        if not parent_ids:
            logger.info(
                f"[Timing][RAG] stage=retrieve_document_total child_count={len(child_docs)} "
                f"parent_count=0 duration={time.perf_counter() - total_t0:.3f}s"
            )
            return child_docs

        try:
            parent_t0 = time.perf_counter()
            parent_map = await parent_chunk_service.get_by_ids(parent_ids)
            logger.info(
                f"[Timing][RAG] stage=parent_fetch requested={len(parent_ids)} "
                f"found={len(parent_map)} duration={time.perf_counter() - parent_t0:.3f}s"
            )
        except Exception as e:
            # 父块查询失败不致命，降级为只用子块
            logger.warning(f"【父子扩展】父块查询失败，降级返回子块: {e}")
            logger.info(
                f"[Timing][RAG] stage=retrieve_document_total child_count={len(child_docs)} "
                f"parent_count=0 duration={time.perf_counter() - total_t0:.3f}s"
            )
            return child_docs

        seen_parents: set = set()
        expanded: List[Document] = []
        for d in child_docs:
            pid = d.metadata.get("parent_id")
            if pid and pid not in seen_parents:
                content = parent_map.get(pid, d.page_content)
                expanded.append(Document(page_content=content, metadata=d.metadata))
                seen_parents.add(pid)
            elif not pid:
                expanded.append(d)
        logger.info(
            f"【父子扩展】{len(child_docs)} 子块 → {len(expanded)} 父块"
            f"（命中 {len(parent_map)}/{len(parent_ids)}）"
        )
        logger.info(
            f"[Timing][RAG] stage=retrieve_document_total child_count={len(child_docs)} "
            f"parent_count={len(expanded)} duration={time.perf_counter() - total_t0:.3f}s"
        )
        return expanded

    # ── 重排序 ────────────────────────────────────────────────────────────────

    @traceable
    async def reorder_documents(self, query: str, documents: list) -> list:
        result = await reorder_service.reorder_documents(query, documents)
        if result["success"]:
            reordered = [doc.get("document", "") for doc in result["documents"]]
            logger.info(f"【RAG】文档重排序成功，返回 {len(reordered)} 个文档")
            return reordered
        else:
            logger.warning(f"【RAG】重排序失败: {result['error']}")
            return documents

    async def get_documents_for_agent(
        self, query: str, filter_meta: Optional[dict] = None
    ) -> Dict[str, Any]:
        """只执行检索、重排序和引用构建，让 Agent 负责最终生成。"""
        total_t0 = time.perf_counter()
        try:
            retrieve_t0 = time.perf_counter()
            documents = await self.retrieve_document(query, filter_meta=filter_meta)
            logger.info(
                f"[Timing][RAG] stage=agent_context_retrieve doc_count={len(documents)} "
                f"duration={time.perf_counter() - retrieve_t0:.3f}s"
            )
        except RetrievalError as e:
            logger.info(
                f"[Timing][RAG] stage=agent_context_total status=retrieval_failed "
                f"duration={time.perf_counter() - total_t0:.3f}s"
            )
            return {
                "documents": [],
                "summary": "知识库检索服务暂时不可用，请稍后再试或联系管理员。",
                "citations": [],
                "error": "retrieval_failed",
                "error_detail": str(e),
            }

        try:
            metadata_map: Dict[str, dict] = {doc.page_content: doc.metadata for doc in documents}
            document_contents = [doc.page_content for doc in documents]

            rerank_t0 = time.perf_counter()
            reorder_result = await reorder_service.reorder_documents(query, document_contents)
            logger.info(
                f"[Timing][RAG] stage=agent_context_rerank doc_count={len(document_contents)} "
                f"duration={time.perf_counter() - rerank_t0:.3f}s"
            )
            if reorder_result["success"]:
                scored_docs: List[Dict] = reorder_result["documents"]
            else:
                logger.warning(f"【RAG】重排序失败: {reorder_result.get('error')}")
                scored_docs = [{"document": c, "similarity": 0.0} for c in document_contents]

            if not scored_docs:
                logger.info(
                    f"[Timing][RAG] stage=agent_context_total status=no_results "
                    f"duration={time.perf_counter() - total_t0:.3f}s"
                )
                return {
                    "documents": [],
                    "summary": "抱歉，我没有找到相关的信息。",
                    "citations": [],
                    "error": None,
                }

            max_score = max(d["similarity"] for d in scored_docs)
            is_enough = max_score >= _GAP_THRESHOLD
            logger.info(
                f"【RAG诊断】max_score={max_score:.4f} 缺口阈值={_GAP_THRESHOLD} "
                f"is_enough={is_enough} doc数={len(scored_docs)}"
            )

            # 低于缺口阈值时不清空 documents：documents=检索到的内容，is_enough=相关度是否达标，
            # 二者解耦。是否记录缺口由 LangGraph 的 route_after_knowledge 依据 is_enough 决定。
            max_documents = 3
            top_scored = scored_docs[:max_documents]
            citations: List[Dict] = []
            citation_t0 = time.perf_counter()
            for d in top_scored:
                meta = metadata_map.get(d["document"], {})
                preview = d["document"]
                if len(preview) > 300:
                    preview = preview[:300] + "…"
                citations.append({
                    "filename": meta.get("filename", "未知文档"),
                    "chunk_preview": preview,
                    "score": round(float(d["similarity"]), 4),
                    "kb_id": meta.get("kb_id"),
                })
            logger.info(
                f"[Timing][RAG] stage=agent_context_citations citation_count={len(citations)} "
                f"duration={time.perf_counter() - citation_t0:.3f}s"
            )

            logger.info(
                f"[Timing][RAG] stage=agent_context_total status={'ok' if is_enough else 'gap'} "
                f"max_score={max_score:.4f} doc_count={len(top_scored)} "
                f"duration={time.perf_counter() - total_t0:.3f}s"
            )
            return {
                "documents": [d["document"] for d in top_scored],
                "summary": "",
                "citations": citations,
                "max_score": max_score,
                "is_enough": is_enough,
                "error": None,
            }

        except Exception as e:
            logger.error(f"【RAG】检索上下文构建失败: {e}", exc_info=True)
            logger.info(
                f"[Timing][RAG] stage=agent_context_total status=failed "
                f"duration={time.perf_counter() - total_t0:.3f}s"
            )
            return {
                "documents": [],
                "summary": "抱歉，处理您的请求时出现了错误。",
                "citations": [],
                "error": "retrieval_failed",
                "error_detail": str(e),
            }

    # ── 综合：检索 + 重排序 + 摘要 ───────────────────────────────────────────

    @traceable
    async def get_documents_and_summary(
        self, query: str, filter_meta: Optional[dict] = None
    ) -> Dict[str, Any]:
        """
        返回 {"documents": [...], "summary": "...", "citations": [...], "error": str|None}

        error 字段语义：
          None              → 正常（可能有命中，也可能"无相关结果"）
          "retrieval_failed"→ 检索系统故障（向量库/BM25/嵌入模型异常）
          "summarize_failed"→ 检索成功但摘要生成失败

        citations 格式：[{"filename": str, "chunk_preview": str, "score": float, "kb_id": str|None}]
        """
        total_t0 = time.perf_counter()
        try:
            retrieve_t0 = time.perf_counter()
            documents = await self.retrieve_document(query, filter_meta=filter_meta)
            logger.info(
                f"[Timing][RAG] stage=summary_retrieve doc_count={len(documents)} "
                f"duration={time.perf_counter() - retrieve_t0:.3f}s"
            )
        except RetrievalError as e:
            logger.info(
                f"[Timing][RAG] stage=summary_total status=retrieval_failed "
                f"duration={time.perf_counter() - total_t0:.3f}s"
            )
            return {
                "documents": [],
                "summary": "知识库检索服务暂时不可用，请稍后再试或联系管理员。",
                "citations": [],
                "error": "retrieval_failed",
                "error_detail": str(e),
            }

        try:
            # content → metadata 映射，用于构建引用
            metadata_map: Dict[str, dict] = {doc.page_content: doc.metadata for doc in documents}
            document_contents = [doc.page_content for doc in documents]

            # 重排序（保留原始分数）
            rerank_t0 = time.perf_counter()
            reorder_result = await reorder_service.reorder_documents(query, document_contents)
            logger.info(
                f"[Timing][RAG] stage=summary_rerank doc_count={len(document_contents)} "
                f"duration={time.perf_counter() - rerank_t0:.3f}s"
            )
            if reorder_result["success"]:
                scored_docs: List[Dict] = reorder_result["documents"]  # [{document, similarity}]
            else:
                logger.warning(f"【RAG】重排序失败: {reorder_result.get('error')}")
                scored_docs = [{"document": c, "similarity": 0.0} for c in document_contents]

            if not scored_docs:
                logger.info(
                    f"[Timing][RAG] stage=summary_total status=no_results "
                    f"duration={time.perf_counter() - total_t0:.3f}s"
                )
                return {
                    "documents": [], "summary": "抱歉，我没有找到相关的信息。",
                    "citations": [], "error": None,
                }

            # 置信度过滤
            max_score = max(d["similarity"] for d in scored_docs)
            logger.info(f"【RAG诊断】max_score={max_score:.4f} 拒答阈值={_CONFIDENCE_THRESHOLD} doc数={len(scored_docs)}")
            if max_score < _CONFIDENCE_THRESHOLD:
                logger.info(f"【RAG】最高置信度 {max_score:.4f} 低于阈值 {_CONFIDENCE_THRESHOLD}，拒绝回答")
                logger.info(
                    f"[Timing][RAG] stage=summary_total status=low_confidence "
                    f"max_score={max_score:.4f} duration={time.perf_counter() - total_t0:.3f}s"
                )
                return {
                    "documents": [],
                    "summary": "抱歉，未在知识库中找到与您问题相关的信息，请尝试换个提问方式或上传相关文档。",
                    "citations": [],
                    "error": None,
                }

            # 构建引用列表（取前 3 名）
            max_documents = 3
            top_scored = scored_docs[:max_documents]
            citations: List[Dict] = []
            citation_t0 = time.perf_counter()
            for d in top_scored:
                meta = metadata_map.get(d["document"], {})
                preview = d["document"]
                if len(preview) > 300:
                    preview = preview[:300] + "…"
                citations.append({
                    "filename": meta.get("filename", "未知文档"),
                    "chunk_preview": preview,
                    "score": round(float(d["similarity"]), 4),
                    "kb_id": meta.get("kb_id"),
                })
            logger.info(
                f"[Timing][RAG] stage=summary_citations citation_count={len(citations)} "
                f"duration={time.perf_counter() - citation_t0:.3f}s"
            )

            reordered_contents = [d["document"] for d in scored_docs]

            # 分批摘要
            try:
                async def summarize_one(i: int, doc: str) -> str:
                    logger.info(f"【RAG】正在总结第{i}个文档")
                    ctx = f"【参考资料{i}】:{doc}\n"
                    t0 = time.time()
                    summary = await asyncio.wait_for(
                        self.chain.ainvoke({"input": query, "context": ctx}),
                        timeout=30.0,
                    )
                    logger.info(f"【RAG】第{i}个文档总结耗时: {time.time()-t0:.2f}秒")
                    return summary

                tasks = [
                    summarize_one(i, doc)
                    for i, doc in enumerate(reordered_contents[:max_documents], 1)
                ]
                t0 = time.time()
                individual_summaries = await asyncio.gather(*tasks)
                logger.info(f"【RAG】所有文档总结完成，总耗时: {time.time()-t0:.2f}秒")

                if len(individual_summaries) == 1:
                    logger.info(
                        f"[Timing][RAG] stage=summary_total status=ok "
                        f"doc_count={len(reordered_contents)} duration={time.perf_counter() - total_t0:.3f}s"
                    )
                    return {
                        "documents": reordered_contents,
                        "summary": individual_summaries[0],
                        "citations": citations,
                        "error": None,
                    }

                combined_context = "以下是多个文档的摘要，请综合这些信息生成最终的回答：\n\n"
                for i, s in enumerate(individual_summaries, 1):
                    combined_context += f"【文档{i}摘要】:{s}\n\n"

                final_t0 = time.perf_counter()
                final_summary = await asyncio.wait_for(
                    self.chain.ainvoke({"input": query, "context": combined_context}),
                    timeout=30.0,
                )
                logger.info(
                    f"[Timing][RAG] stage=final_summary_generate "
                    f"duration={time.perf_counter() - final_t0:.3f}s"
                )
                logger.info(
                    f"[Timing][RAG] stage=summary_total status=ok "
                    f"doc_count={len(reordered_contents)} duration={time.perf_counter() - total_t0:.3f}s"
                )
                return {
                    "documents": reordered_contents,
                    "summary": final_summary,
                    "citations": citations,
                    "error": None,
                }

            except asyncio.TimeoutError:
                logger.error("【RAG】生成摘要超时")
                logger.info(
                    f"[Timing][RAG] stage=summary_total status=timeout "
                    f"duration={time.perf_counter() - total_t0:.3f}s"
                )
                return {
                    "documents": reordered_contents,
                    "summary": "抱歉，生成摘要超时，请稍后再试。",
                    "citations": citations,
                    "error": "summarize_failed",
                }

        except Exception as e:
            logger.error(f"【RAG】摘要阶段失败: {e}", exc_info=True)
            logger.info(
                f"[Timing][RAG] stage=summary_total status=failed "
                f"duration={time.perf_counter() - total_t0:.3f}s"
            )
            return {
                "documents": [], "summary": "抱歉，处理您的请求时出现了错误。",
                "citations": [], "error": "summarize_failed",
            }

    @traceable
    async def rag_summary(self, query: str, filter_meta: Optional[dict] = None) -> str:
        result = await self.get_documents_and_summary(query, filter_meta=filter_meta)
        return result.get("summary", "抱歉，处理您的请求时出现了错误。")


rag_service = RagService()


if __name__ == '__main__':
    async def main():
        await rag_service.initialize_retriever()
        result = await rag_service.rag_summary("小户型适合什么扫地机器人")
        print(result)

    asyncio.run(main())
