"""
持续更新调度器

内置两类任务：
1. folder_watch_job  —— 定期扫描 watched_dir，自动向量化新增文件（系统知识库）
2. (扩展示例) external_source_job —— 拉取外部 URL / API 内容（留空，按需实现）

配置（通过环境变量）：
  SCHEDULER_ENABLED=true          是否启用调度器（默认 false）
  SCHEDULER_WATCH_DIR=data/watch  要监控的目录（默认 data/watch）
  SCHEDULER_INTERVAL_MINUTES=10   扫描间隔分钟数（默认 10）
"""
import asyncio
import os
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.logger_handler import logger
from app.rag.rag_service import rag_service
from app.rag.vector_store import VectorStoreService
from app.utils.config import chroma_config

# 系统级上传用 user_id（不属于任何个人用户）
SYSTEM_USER_ID = "__system__"


async def folder_watch_job():
    """
    扫描 watched_dir，将尚未入库的文件自动向量化。
    使用 SYSTEM_USER_ID 标记，所有用户均可检索。
    """
    watch_dir = os.getenv("SCHEDULER_WATCH_DIR", "data/watch")
    watch_path = Path(watch_dir)

    if not watch_path.exists():
        watch_path.mkdir(parents=True, exist_ok=True)
        return

    allowed_exts = set(chroma_config.get("allow_knowledge_file_types", ["txt", "pdf", "md", "docx", "pptx"]))
    candidates = [
        p for p in watch_path.iterdir()
        if p.is_file() and p.suffix.lstrip(".").lower() in allowed_exts
    ]

    if not candidates:
        return

    logger.info(f"[Scheduler] 目录扫描到 {len(candidates)} 个文件，开始处理")
    store = VectorStoreService()

    # 构造伪 UploadFile 替代品：从磁盘文件路径直接入库
    from app.services.document_service import document_service
    from app.utils.file_handler import get_file_md5_hex

    new_count = 0
    for path in candidates:
        try:
            md5_hex = await get_file_md5_hex(str(path))
            if await document_service.md5_exists(SYSTEM_USER_ID, md5_hex):
                continue  # 已入库，跳过

            # 直接复用 vector_store 的底层路径处理
            docs = await store.get_file_document(str(path))
            if not docs:
                continue

            import uuid
            chunks = await store.spliter.split_documents(docs)
            doc_id = str(uuid.uuid4())
            for chunk in chunks:
                chunk.metadata["file_id"] = doc_id
                chunk.metadata["filename"] = path.name
                chunk.metadata["user_id"] = SYSTEM_USER_ID

            import asyncio as _asyncio
            await _asyncio.to_thread(store.vectors_store.add_documents, chunks)
            await document_service.save_record(
                doc_id=doc_id,
                user_id=SYSTEM_USER_ID,
                filename=path.name,
                md5_hex=md5_hex,
                file_size=path.stat().st_size,
                chunk_count=len(chunks),
            )
            new_count += 1
            logger.info(f"[Scheduler] 自动入库: {path.name}，{len(chunks)} chunks")
        except Exception as e:
            logger.error(f"[Scheduler] 处理 {path.name} 失败: {e}", exc_info=True)

    if new_count > 0:
        rag_service.invalidate_retriever()
        logger.info(f"[Scheduler] 本轮新增 {new_count} 个文件，已失效检索器缓存")


# ── 调度器实例（全局单例）────────────────────────────────────────────────────

_scheduler: AsyncIOScheduler | None = None


def create_scheduler() -> AsyncIOScheduler:
    interval_minutes = int(os.getenv("SCHEDULER_INTERVAL_MINUTES", "10"))
    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        folder_watch_job,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id="folder_watch",
        name="目录监控自动入库",
        replace_existing=True,
        misfire_grace_time=60,
    )

    # ── 扩展点：外部数据源（按需取消注释并实现）───────────────────────────────
    # scheduler.add_job(
    #     external_source_job,
    #     trigger=IntervalTrigger(hours=1),
    #     id="external_source",
    #     name="外部数据源同步",
    # )

    return scheduler


def start_scheduler():
    global _scheduler
    if not os.getenv("SCHEDULER_ENABLED", "false").lower() == "true":
        logger.info("[Scheduler] 调度器未启用（SCHEDULER_ENABLED != true）")
        return
    _scheduler = create_scheduler()
    _scheduler.start()
    logger.info(
        f"[Scheduler] 调度器已启动，监控目录: {os.getenv('SCHEDULER_WATCH_DIR', 'data/watch')}，"
        f"间隔: {os.getenv('SCHEDULER_INTERVAL_MINUTES', '10')} 分钟"
    )


def stop_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[Scheduler] 调度器已停止")
