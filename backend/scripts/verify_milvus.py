"""Milvus 端到端验证脚本。

前置条件：
  1. docker compose -f docker-compose.milvus.yml up -d 已就绪
  2. MySQL 正在运行（用于 ChildChunk 表）
  3. .env 设置 VECTOR_STORE_BACKEND=milvus

跑法：
  cd backend && .venv/Scripts/python.exe -m scripts.verify_milvus
"""
import asyncio
import os

from dotenv import load_dotenv
from langchain_core.documents import Document

load_dotenv()

if os.getenv("VECTOR_STORE_BACKEND", "").lower() != "milvus":
    raise SystemExit("请先在 .env 设置 VECTOR_STORE_BACKEND=milvus 再跑此脚本")


async def main() -> None:
    from app.db.db_config import init_db
    from app.rag.vector_backend import build_backend
    from app.services.child_chunk_service import child_chunk_service

    print("→ 1. 初始化 MySQL 表（含 child_chunks）")
    await init_db()

    print("→ 2. 构建 MilvusBackend")
    backend = build_backend()

    print("→ 3. 准备 3 个测试子块")
    docs = [
        Document(page_content="今天天气真好", metadata={
            "file_id": "verify-doc-1",
            "user_id": "verify-user-A",
            "kb_id": None,
            "filename": "test1.txt",
            "chunk_index": 0,
        }),
        Document(page_content="向量检索是 RAG 的核心", metadata={
            "file_id": "verify-doc-1",
            "user_id": "verify-user-A",
            "kb_id": None,
            "filename": "test1.txt",
            "chunk_index": 1,
        }),
        Document(page_content="别人的文档不应被检索到", metadata={
            "file_id": "verify-doc-2",
            "user_id": "verify-user-B",
            "kb_id": None,
            "filename": "test2.txt",
            "chunk_index": 0,
        }),
    ]

    print("→ 4. 写入 MySQL + Milvus")
    await child_chunk_service.save_batch(docs)
    await backend.add_documents(docs)

    print("→ 5. 用 user_id=verify-user-A 做检索")
    retriever = await backend.as_retriever(
        k=5,
        filter_meta={"user_id": {"$eq": "verify-user-A"}},
    )
    results = await retriever.ainvoke("RAG 检索")
    print(f"   命中 {len(results)} 条")
    for r in results:
        print(f"   - {r.page_content!r} meta={r.metadata}")
    assert all(r.metadata.get("user_id") == "verify-user-A" for r in results), \
        "FAIL：filter 未生效，跨用户结果泄漏！"

    print("→ 6. 按 file_id 删除 verify-doc-1")
    await backend.delete_by_filter({"file_id": "verify-doc-1"})
    await child_chunk_service.delete_by_doc_id("verify-doc-1")

    print("→ 7. 清理 verify-user-B")
    await backend.delete_by_filter({"user_id": "verify-user-B"})
    await child_chunk_service.delete_by_user("verify-user-B")

    print("\n✅ Milvus 端到端验证通过")


if __name__ == "__main__":
    asyncio.run(main())
