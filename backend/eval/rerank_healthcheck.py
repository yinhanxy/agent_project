"""rerank 健康检查：验证当前 RERANKER 配置可用，并打印一组样例的相关度分数。

用法（backend 目录，需 DashScope key + 网络）：
    .\\.venv\\Scripts\\python.exe -m eval.rerank_healthcheck
判读：success=True 且相关文档分数明显高于无关文档 → 模型有效；
      若 success=False 或分数全 0/全等 → 模型名失效或调用异常，需查 ALIYUN_RERANKER_MODEL_NAME。
"""
import asyncio
from app.rag.reorder_service import reorder_service

_SAMPLES = [
    ("一线城市出差住宿费上限",
     ["一线城市出差住宿费每晚上限550元", "笔记本电脑每4年更换一次", "年假按工龄计算"]),
    ("远程办公申请条件",
     ["远程办公需转正满3个月且绩效不低于B", "差旅报销时限60天", "病假需提供证明"]),
]


async def main():
    for query, docs in _SAMPLES:
        res = await reorder_service.reorder_documents(query, docs)
        print(f"\nquery={query!r} success={res['success']} error={res.get('error','')}")
        for item in res.get("documents", []):
            print(f"  {item['similarity']:.4f}  {item['document'][:30]}")


if __name__ == "__main__":
    asyncio.run(main())
