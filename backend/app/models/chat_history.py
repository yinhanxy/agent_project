from sqlalchemy import Boolean, Column, Integer, String, Text, DateTime, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
import uuid

Base = declarative_base()

class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(String(64), primary_key=True, index=True)
    # 通过 user_id 关联用户微服务，不做物理外键约束
    user_id = Column(String(64), index=True, nullable=False)

    title = Column(String(255), default="新的对话")
    metadata_ = Column(JSON, name="metadata")  # metadata 是 SQL 保留字，加下划线
    archived = Column(Boolean, nullable=False, default=False, server_default="0", index=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 关系
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), ForeignKey("chat_sessions.id"))

    # LangChain 标准字段
    role = Column(String(32), nullable=False)
    content = Column(Text, nullable=False)
    metadata_ = Column(JSON, name="metadata")

    created_at = Column(DateTime(timezone=True), server_default=func.now()) 

    # 关系
    session = relationship("ChatSession", back_populates="messages")


class KnowledgeBase(Base):
    """企业知识库实体：company / dept / personal 三级共享"""
    __tablename__ = "knowledge_bases"

    kb_id = Column(String(64), primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    owner_id = Column(String(64), nullable=False, index=True)
    scope = Column(String(20), nullable=False, default="personal")  # personal/dept/company/admin
    dept_id = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class KBPermission(Base):
    """知识库成员权限：viewer / editor / admin"""
    __tablename__ = "kb_permissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    kb_id = Column(String(64), nullable=False, index=True)
    principal_id = Column(String(64), nullable=False)   # user_id 或 dept_id
    principal_type = Column(String(20), nullable=False, default="user")  # user / dept
    role = Column(String(20), nullable=False, default="viewer")  # viewer/editor/admin
    granted_by = Column(String(64), nullable=True)
    granted_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("kb_id", "principal_id", "principal_type", name="uk_kb_principal"),
    )


class DocumentRecord(Base):
    """记录用户上传到知识库的文档元信息"""
    __tablename__ = "document_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # 文件级唯一 ID，同时作为向量库各 chunk 的 file_id 元数据值
    doc_id = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(String(64), nullable=False, index=True)
    kb_id = Column(String(64), nullable=True, index=True)   # NULL = 个人文档
    filename = Column(String(500), nullable=False)
    md5_hex = Column(String(32), nullable=False)
    file_size = Column(Integer, default=0)
    chunk_count = Column(Integer, default=0)
    upload_time = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = ()


class ParentChunk(Base):
    """父子检索中的父级大块，存储完整上下文供 LLM 使用"""
    __tablename__ = "parent_chunks"

    parent_id = Column(String(128), primary_key=True, comment="格式: {doc_id}_p{index}")
    doc_id = Column(String(64), nullable=False, index=True)
    user_id = Column(String(64), nullable=False, index=True)
    content = Column(Text, nullable=False)
    chunk_index = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ChildChunk(Base):
    """子块文本镜像表。

    向量库只存 embedding + metadata；BM25 索引需要全量子块文本与 metadata，
    单独存在 MySQL 这里，避免依赖向量库的 list-all 能力。
    """
    __tablename__ = "child_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chunk_id = Column(String(128), unique=True, nullable=False, index=True,
                      comment="向量库中该子块的主键，用于反查")
    user_id = Column(String(64), nullable=False, index=True)
    kb_id = Column(String(64), nullable=True, index=True)
    file_id = Column(String(64), nullable=False, index=True,
                     comment="该子块所属的文档 ID（等同 doc_id，与向量库 metadata key 对齐）")
    parent_id = Column(String(128), nullable=True, index=True,
                       comment="父块 ID（semantic 模式下为空）")
    filename = Column(String(500), nullable=True)
    content = Column(Text, nullable=False)
    chunk_index = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class KnowledgeGap(Base):
    """知识缺口记录：检索不足或被判定为缺口类问题时生成，供管理员补充知识库。"""
    __tablename__ = "knowledge_gaps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)   # 缺口产生者
    dept_id = Column(String(64), nullable=True, index=True)    # 部门归属（备用）
    title = Column(String(255), nullable=False)
    question = Column(Text, nullable=False)                    # 去重键之一
    category = Column(String(64), default="unknown")
    suggested_content = Column(Text, default="")
    status = Column(String(20), nullable=False, default="pending")  # pending/reviewed/resolved/ignored
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AgentTrace(Base):
    """多 agent 协同轨迹：每个节点一行，供事后复盘。实时展示仍走 SSE，不依赖查库。"""
    __tablename__ = "agent_traces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), index=True, nullable=False)
    agent_name = Column(String(64), nullable=False)
    output = Column(Text, default="")
    status = Column(String(20), nullable=False, default="done")  # done/failed/skipped
    seq = Column(Integer, default=0)   # 同 session 内顺序
    created_at = Column(DateTime(timezone=True), server_default=func.now())
