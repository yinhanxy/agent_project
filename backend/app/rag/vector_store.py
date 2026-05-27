"""
向量存储服务（后端可切换：Chroma / Milvus）

切片策略：
  .md 文件      → semantic（Markdown 标题边界 + 固定细切）
  其他格式       → parent_child（父块→MySQL，子块→向量库 + ChildChunk 镜像）
  BM25 索引构建 → 从 MySQL ChildChunk 表拉取（不再依赖向量库的 list-all）
"""
import asyncio
import os
import sys
import tempfile
import uuid

import jieba
from langchain_classic.retrievers import EnsembleRetriever
from langchain_core.documents import Document
from langchain_community.retrievers import BM25Retriever


def _bm25_preprocess(text: str) -> list:
    """BM25 中文分词预处理：默认 .split() 在中文上几乎无效，
    退化成整段当一个 token，导致排序失真。用 jieba 切词后再喂给 BM25。
    """
    return [tok for tok in jieba.cut(text) if tok.strip()]

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.rag.text_spliter import SmartTextSplitter
from app.rag.vector_backend import build_backend
from app.services.document_service import document_service
from app.services.parent_chunk_service import parent_chunk_service
from app.services.child_chunk_service import child_chunk_service
from app.utils.config import chroma_config
from app.utils.factory import embed_model
from app.utils.file_handler import (
    pdf_loader, txt_loader, listdir_allowed_type,
    get_file_md5_hex, markdown_loader, ppt_loader, word_loader,
)
from app.core.logger_handler import logger


class VectorStoreService:

    def __init__(self):
        self.backend = build_backend()
        self.splitter = SmartTextSplitter(embedding_model=embed_model)

    # ── 检索器 ────────────────────────────────────────────────────────────────

    async def get_bm25_retriever(self, filter_meta: dict = None):
        """BM25 从 MySQL ChildChunk 拉子块，按 filter_meta 缩小范围。
        中文使用 jieba 分词，否则 BM25 在中文 query 上会退化成噪声排序。
        """
        user_id, kb_ids = self._extract_user_and_kbs(filter_meta)
        docs = await child_chunk_service.load_filtered(user_id=user_id, kb_ids=kb_ids)
        if not docs:
            return None
        return BM25Retriever.from_documents(
            documents=docs,
            k=chroma_config["k"],
            preprocess_func=_bm25_preprocess,
        )

    async def get_retriever(self, query: str = None, filter_meta: dict = None):
        vector_retriever = await self.backend.as_retriever(
            k=chroma_config["k"],
            filter_meta=filter_meta,
        )
        bm25_retriever = await self.get_bm25_retriever(filter_meta=filter_meta)
        if bm25_retriever:
            weights = await self._dynamic_weights(query)
            return EnsembleRetriever(
                retrievers=[vector_retriever, bm25_retriever],
                weights=weights,
            )
        return vector_retriever

    @staticmethod
    def _extract_user_and_kbs(filter_meta: dict = None) -> tuple:
        """从 _build_rag_filter 产出的 dict 里抽 user_id 与 kb_ids。

        预期形态：
          {"$or": [{"user_id": {"$eq": "..."}},
                   {"kb_id": {"$in": [...]}}]}
        或：
          {"user_id": {"$eq": "..."}}
        """
        if not filter_meta:
            return None, None
        user_id = None
        kb_ids: list = []

        def walk(node):
            nonlocal user_id, kb_ids
            if not isinstance(node, dict):
                return
            for k, v in node.items():
                if k == "$or" or k == "$and":
                    for sub in v:
                        walk(sub)
                elif k == "user_id":
                    if isinstance(v, dict) and "$eq" in v:
                        user_id = v["$eq"]
                    elif isinstance(v, str):
                        user_id = v
                elif k == "kb_id":
                    if isinstance(v, dict) and "$in" in v:
                        kb_ids.extend(v["$in"])
                    elif isinstance(v, str):
                        kb_ids.append(v)

        walk(filter_meta)
        return user_id, (kb_ids or None)

    @staticmethod
    async def _dynamic_weights(query: str = None):
        if not query:
            return [0.5, 0.5]
        length = len(query)
        v, b = (0.7, 0.3) if length > 50 else (0.3, 0.7) if length < 20 else (0.5, 0.5)
        words = len(query.split())
        if words > 0 and words / length > 0.1:
            b, v = min(b + 0.1, 0.7), max(v - 0.1, 0.3)
        return [v, b]

    # ── 文档写入 ──────────────────────────────────────────────────────────────

    async def get_document(
        self,
        files: list = None,
        user_id: str = None,
        replace: bool = False,
        kb_id: str = None,
    ) -> dict:
        """
        处理上传文件：写入向量库（子块）+ MySQL（父块 + 子块镜像 + 记录）。
        切片策略：.md → semantic；其他 → parent_child
        """
        file_paths: list[tuple[str, str, int]] = []

        if files:
            for file in files:
                suffix = os.path.splitext(file.filename)[1]
                tmp = await asyncio.to_thread(
                    tempfile.NamedTemporaryFile, delete=False, suffix=suffix
                )
                content = await file.read()
                await asyncio.to_thread(tmp.write, content)
                await asyncio.to_thread(tmp.close)
                file_paths.append((tmp.name, file.filename, len(content)))
        else:
            allowed = await listdir_allowed_type(
                chroma_config["data_path"],
                tuple(chroma_config["allow_knowledge_file_types"]),
            )
            for p in allowed:
                file_paths.append((p, os.path.basename(p), 0))

        processed = []
        duplicates = []

        for file_path, original_name, file_size in file_paths:
            is_tmp = bool(files)
            try:
                md5_hex = await get_file_md5_hex(file_path)

                if replace and user_id:
                    old = await document_service.get_by_filename(user_id, original_name, kb_id=kb_id)
                    if old:
                        if old.md5_hex == md5_hex:
                            logger.info(f"[VectorStore] {original_name} 内容未变化，跳过")
                            duplicates.append(original_name)
                            continue
                        logger.info(f"[VectorStore] 替换 {original_name}，删除旧 doc_id={old.doc_id}")
                        await self.delete_document_by_id(old.doc_id, user_id)
                    elif await document_service.md5_exists(user_id, md5_hex, kb_id=kb_id):
                        logger.info(f"[VectorStore] {original_name} 内容已存在，跳过")
                        duplicates.append(original_name)
                        continue

                elif user_id and await document_service.md5_exists(user_id, md5_hex, kb_id=kb_id):
                    logger.info(f"[VectorStore] {original_name} MD5 已存在，跳过")
                    duplicates.append(original_name)
                    continue

                docs: list[Document] = await self.get_file_document(file_path)
                if not docs:
                    logger.error(f"[VectorStore] {original_name} 加载为空，跳过")
                    continue

                doc_id = str(uuid.uuid4())
                for d in docs:
                    d.metadata.setdefault("filename", original_name)
                    if user_id:
                        d.metadata.setdefault("user_id", user_id)
                    if kb_id:
                        d.metadata.setdefault("kb_id", kb_id)

                ext = os.path.splitext(original_name)[1].lower()
                if ext == ".md":
                    chunks = await self.splitter.split_semantic(docs)
                    for c in chunks:
                        c.metadata["file_id"] = doc_id
                    parent_docs = []
                    child_docs = chunks
                else:
                    child_docs, parent_docs = await self.splitter.split_parent_child(docs, doc_id)
                    for c in child_docs:
                        c.metadata["file_id"] = doc_id
                        if user_id:
                            c.metadata.setdefault("user_id", user_id)
                    for p in parent_docs:
                        p.metadata["doc_id"] = doc_id
                        if user_id:
                            p.metadata.setdefault("user_id", user_id)

                if not child_docs:
                    logger.error(f"[VectorStore] {original_name} 切片为空，跳过")
                    continue

                # 1) 先写 MySQL ChildChunk，生成 chunk_id 并回填 metadata
                await child_chunk_service.save_batch(child_docs)

                # 2) 再写向量库（metadata 已含 chunk_id，两边对齐）
                await self.backend.add_documents(child_docs)

                # 3) 父块写 MySQL
                if parent_docs:
                    await parent_chunk_service.save_batch(parent_docs)

                # 4) 文档记录
                if user_id:
                    await document_service.save_record(
                        doc_id=doc_id,
                        user_id=user_id,
                        filename=original_name,
                        md5_hex=md5_hex,
                        file_size=file_size,
                        chunk_count=len(child_docs),
                        kb_id=kb_id,
                    )

                processed.append(doc_id)
                logger.info(
                    f"[VectorStore] {original_name} → doc_id={doc_id}，"
                    f"{len(child_docs)} 子块，{len(parent_docs)} 父块"
                )

            except Exception as e:
                logger.error(f"[VectorStore] {original_name} 处理失败: {e}", exc_info=True)
            finally:
                if is_tmp:
                    try:
                        os.unlink(file_path)
                    except Exception:
                        pass

        return {"processed": processed, "duplicates": duplicates}

    # ── 删除 ─────────────────────────────────────────────────────────────────

    async def delete_document_by_id(self, doc_id: str, user_id: str) -> bool:
        """删除单个文档（向量库 + MySQL 父块/子块/记录）"""
        try:
            await self.backend.delete_by_filter({"file_id": doc_id})
            await child_chunk_service.delete_by_doc_id(doc_id)
            await parent_chunk_service.delete_by_doc_id(doc_id)
            await document_service.delete_by_doc_id(doc_id, user_id)
            logger.info(f"[VectorStore] 已删除 doc_id={doc_id}")
            return True
        except Exception as e:
            logger.error(f"[VectorStore] 删除 doc_id={doc_id} 失败: {e}", exc_info=True)
            return False

    async def delete_user_documents(self, user_id: str) -> None:
        """清空某用户全部文档"""
        try:
            await self.backend.delete_by_filter({"user_id": user_id})
            await child_chunk_service.delete_by_user(user_id)
            await parent_chunk_service.delete_by_user(user_id)
            await document_service.delete_by_user(user_id)
            logger.info(f"[VectorStore] 已清空用户 {user_id} 的所有文档")
        except Exception as e:
            logger.error(f"[VectorStore] 清空用户 {user_id} 失败: {e}", exc_info=True)
            raise

    # ── 内部工具 ──────────────────────────────────────────────────────────────

    async def get_file_document(self, read_path: str) -> list[Document]:
        ext = read_path.lower()
        if ext.endswith(".txt"):   return await txt_loader(read_path)
        if ext.endswith(".pdf"):   return await pdf_loader(read_path)
        if ext.endswith(".md"):    return await markdown_loader(read_path)
        if ext.endswith(".pptx"):  return await ppt_loader(read_path)
        if ext.endswith(".docx"):  return await word_loader(read_path)
        return []
