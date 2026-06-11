"""幂等把 docs/test-corpus 灌入向量库，供评估检索。

用法（在 backend 目录）：
    .\.venv\Scripts\python.exe -m eval.seed_corpus
重复执行安全：vector_store 按 MD5 去重，已灌的文件自动跳过。
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
    files = [_LocalFile(p) for p in sorted(CORPUS_DIR.glob("*.md"))]
    if not files:
        raise SystemExit(f"未在 {CORPUS_DIR} 找到 .md 语料")
    vs = VectorStoreService()
    result = await vs.get_document(files=files, user_id=EVAL_USER_ID, kb_id=None)
    print(f"[seed] processed={result['processed']} duplicates={result['duplicates']}")


if __name__ == "__main__":
    asyncio.run(main())
