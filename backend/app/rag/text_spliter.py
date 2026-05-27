"""
SmartTextSplitter —— 三策略智能切片器

策略选择：
  fixed        固定大小 + 重叠（兜底）
  semantic     先按文档结构边界切（Markdown 标题 / 编号章节），再 fixed 细切
  parent_child 两级切片：大父块存 MySQL，小子块存 ChromaDB，检索时子→父扩展

语言适配：
  自动统计中文字符占比，>15% 视为中文，使用中文友好参数和分隔符。

用法：
  splitter = SmartTextSplitter(embedding_model=embed_model)

  # 兜底模式（BM25 索引等场景）
  fixed_chunks = await splitter.split_fixed(docs)

  # 结构化文档（.md 文件）
  semantic_chunks = await splitter.split_semantic(docs)

  # 高质量场景（PDF / DOCX / PPTX 上传）
  child_chunks, parent_chunks = await splitter.split_parent_child(docs, doc_id)
"""
import re
import asyncio
from typing import List, Tuple, Optional, Any

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter


# ── 语言配置 ──────────────────────────────────────────────────────────────────

_ZH_CONFIG = {
    "fixed_size": 500,
    "fixed_overlap": 80,
    "parent_size": 800,
    "child_size": 150,
    "child_overlap": 20,
    # 优先在中文句末、段落边界处切割
    "separators": ["\n\n", "\n", "。", "！", "？", "；", "……", "—", "，", " ", ""],
}

_EN_CONFIG = {
    "fixed_size": 800,
    "fixed_overlap": 120,
    "parent_size": 1500,
    "child_size": 300,
    "child_overlap": 60,
    "separators": ["\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " ", ""],
}

# Markdown 标题级别
_MD_HEADERS = [("#", "h1"), ("##", "h2"), ("###", "h3"), ("####", "h4")]


class SmartTextSplitter:

    def __init__(self, embedding_model: Optional[Embeddings] = None):
        self.embedding_model = embedding_model  # 保留接口，暂未用于优化

    # ── 语言 / 结构检测 ───────────────────────────────────────────────────────

    @staticmethod
    def detect_language(text: str) -> str:
        """统计中文字符占比，>15% 返回 'zh'，否则 'en'"""
        if not text:
            return "en"
        zh = sum(1 for c in text if "一" <= c <= "鿿")
        return "zh" if zh / len(text) > 0.15 else "en"

    @staticmethod
    def has_markdown_headers(text: str) -> bool:
        return bool(re.search(r"^#{1,4}\s+\S", text, re.MULTILINE))

    @staticmethod
    def has_numbered_sections(text: str) -> bool:
        """检测编号章节，如 '1. 概述'、'第一章'"""
        return bool(
            re.search(r"^(\d+\.|\d+\.\d+|第[一二三四五六七八九十百]+[章节])\s", text, re.MULTILINE)
        )

    # ── 构建 LangChain 切割器 ─────────────────────────────────────────────────

    @staticmethod
    def _make_splitter(size: int, overlap: int, cfg: dict) -> RecursiveCharacterTextSplitter:
        return RecursiveCharacterTextSplitter(
            chunk_size=size,
            chunk_overlap=overlap,
            separators=cfg["separators"],
        )

    def _get_cfg(self, docs: List[Document]) -> dict:
        sample = " ".join(d.page_content for d in docs[:5])
        lang = self.detect_language(sample)
        return _ZH_CONFIG if lang == "zh" else _EN_CONFIG

    # ── 三种公开切片方法 ──────────────────────────────────────────────────────

    async def split_fixed(self, docs: List[Document]) -> List[Document]:
        """
        兜底策略：RecursiveCharacterTextSplitter，按语言选参数。
        适用：BM25 索引构建、纯文本 txt。
        """
        if not docs:
            return []
        cfg = self._get_cfg(docs)
        splitter = self._make_splitter(cfg["fixed_size"], cfg["fixed_overlap"], cfg)
        return await asyncio.to_thread(splitter.split_documents, docs)

    async def split_semantic(self, docs: List[Document]) -> List[Document]:
        """
        语义边界策略：有 Markdown 标题则先按标题拆，再 fixed 细切；
        有编号章节则调大切割粒度以保留章节完整性；否则退化为 fixed。
        适用：.md 文件，或有明确标题结构的 PDF。
        """
        if not docs:
            return []
        cfg = self._get_cfg(docs)
        full_text = "\n".join(d.page_content for d in docs)

        if self.has_markdown_headers(full_text):
            header_splitter = MarkdownHeaderTextSplitter(
                headers_to_split_on=_MD_HEADERS,
                strip_headers=False,
            )
            section_docs: List[Document] = []
            for doc in docs:
                sections = await asyncio.to_thread(header_splitter.split_text, doc.page_content)
                for s in sections:
                    merged_meta = {**doc.metadata, **s.metadata}
                    section_docs.append(Document(page_content=s.page_content, metadata=merged_meta))

            # 标题段落内再做 fixed 细切，防止单节过长
            fine = self._make_splitter(cfg["fixed_size"], cfg["fixed_overlap"], cfg)
            return await asyncio.to_thread(fine.split_documents, section_docs)

        if self.has_numbered_sections(full_text):
            # 编号章节：适当放大粒度保留语义完整性
            big_size = int(cfg["fixed_size"] * 1.4)
            splitter = self._make_splitter(big_size, cfg["fixed_overlap"], cfg)
            return await asyncio.to_thread(splitter.split_documents, docs)

        # 无明显结构，退化为 fixed
        return await self.split_fixed(docs)

    async def split_parent_child(
        self, docs: List[Document], doc_id: str
    ) -> Tuple[List[Document], List[Document]]:
        """
        父子切片策略（高质量场景）。

        父块：较大，供 LLM 生成答案时使用完整上下文。
        子块：较小，供向量检索精准召回。

        返回 (child_docs, parent_docs)：
          - child_docs  → 存入 ChromaDB（含 parent_id 元数据）
          - parent_docs → 存入 MySQL parent_chunks 表
        """
        if not docs:
            return [], []

        cfg = self._get_cfg(docs)

        # 第一级：切父块（较大，不重叠，保留完整段落）
        parent_splitter = self._make_splitter(cfg["parent_size"], 0, cfg)
        parent_raw: List[Document] = await asyncio.to_thread(
            parent_splitter.split_documents, docs
        )

        # 第二级：每个父块切子块（较小，有重叠）
        child_splitter = self._make_splitter(cfg["child_size"], cfg["child_overlap"], cfg)

        parent_docs: List[Document] = []
        child_docs: List[Document] = []

        for p_idx, p_doc in enumerate(parent_raw):
            parent_id = f"{doc_id}_p{p_idx}"
            # 注入父块元数据
            p_doc.metadata.update({"parent_id": parent_id, "doc_id": doc_id, "chunk_index": p_idx})
            parent_docs.append(p_doc)

            # 切子块，继承父块元数据并加 parent_id
            children: List[Document] = await asyncio.to_thread(
                child_splitter.split_documents, [p_doc]
            )
            for child in children:
                child.metadata["parent_id"] = parent_id
                child.metadata["chunk_index"] = p_idx
            child_docs.extend(children)

        return child_docs, parent_docs

    # ── 向后兼容接口（旧代码调用 split_documents）────────────────────────────

    async def split_documents(self, docs: List[Any]) -> List[Any]:
        """向后兼容：等价于 split_fixed，供 BM25 等场景直接调用"""
        return await self.split_fixed(docs)
