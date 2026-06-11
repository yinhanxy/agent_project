r"""幂等把 docs/test-corpus 灌入向量库，供评估检索。

用法（在 backend 目录）：
    .\.venv\Scripts\python.exe -m eval.seed_corpus
重置式：每次先清空 EVAL_USER_ID 旧文档再灌，确保语料确定、可复现。
"""
import asyncio
import os
from pathlib import Path

from app.rag.vector_store import VectorStoreService

EVAL_USER_ID = "eval-bot"
CORPUS_DIR = Path(__file__).resolve().parents[2] / "docs" / "test-corpus"


class _LocalFile:
    """伪 UploadFile：vector_store.get_document 只用到 .filename 与 await .read()。"""
    def __init__(self, path: Path):
        self.filename = path.name
        self._path = path

    async def read(self) -> bytes:
        return await asyncio.to_thread(self._path.read_bytes)


async def main():
    files = [_LocalFile(p) for p in sorted(CORPUS_DIR.glob("*.md"))
             if p.name.lower() != "readme.md"]
    if not files:
        raise SystemExit(f"未在 {CORPUS_DIR} 找到 .md 语料")
    vs = VectorStoreService()
    # 重置式灌库：先清空评估用户旧文档（含历史误灌的 README），保证语料确定、可复现
    await vs.delete_user_documents(EVAL_USER_ID)
    result = await vs.get_document(files=files, user_id=EVAL_USER_ID, kb_id=None)
    print(f"[seed] reset+processed={result['processed']} duplicates={result['duplicates']}")


if __name__ == "__main__":
    asyncio.run(main())
