# ChromaDB → Milvus 切换指南

## 架构概览

向量库通过 `VECTOR_STORE_BACKEND` 环境变量切换：
- `chroma`（默认）：嵌入式，数据落在 `backend/data/chromadb`
- `milvus`：独立服务，数据落在项目根 `data/milvus/`，通过 19530 端口连接

BM25 索引数据已剥离到 MySQL `child_chunks` 表，与向量库后端无关。

## 切换步骤

### 1. 启动 Milvus

```bash
# 项目根目录
docker compose -f docker-compose.milvus.yml up -d

# 等 ~90 秒，检查健康
docker ps --filter "name=rag-milvus"
```

三个容器（etcd / minio / milvus）应当都 `Up (healthy)`。

### 2. 修改 `backend/.env`

```bash
VECTOR_STORE_BACKEND=milvus
MILVUS_HOST=localhost
MILVUS_PORT=19530
```

### 3. （可选）跑验证脚本

```bash
cd backend
.venv/Scripts/python.exe -m scripts.verify_milvus
```

最后一行应打印 `✅ Milvus 端到端验证通过`。

### 4. 启动服务

正常 `uvicorn main:app` 即可。首次启动会自动建 `child_chunks` 表与 Milvus 集合。

## ⚠️ 升级注意（重要）

本次重构把 BM25 索引数据源从向量库迁移到了 MySQL 新表 `child_chunks`。**无论是否切换到 Milvus**，从此版本之前升级的部署都需要注意：

- 旧文档在 Chroma（或将来 Milvus）里有向量数据，但 `child_chunks` 表是空的
- 这会导致 BM25 检索完全失效，系统**静默降级**为纯向量检索（不会报错，但召回质量下降）
- **解决方案**：升级后让用户重新上传所有文档（首次重新写入会同时建立向量与 `child_chunks` 镜像）

如果不想清空重传，可以写一次性回填脚本：从 ChromaDB 的 `vector_store.get(include=["documents","metadatas"])` 拉所有子块，调 `child_chunk_service.save_batch(...)` 镜像到 MySQL。本仓库未提供，需要自行实现。

## 数据迁移

**当前策略：清空重传**。Chroma 中原有数据不会自动搬迁，旧用户的知识库需重新上传。

如要保留旧数据：
1. 删除 `backend/data/chromadb` 目录
2. 清空 MySQL 表：`document_records` / `parent_chunks` / `child_chunks`
3. 让用户重新上传所有文档

## 回滚

```bash
# 改回 chroma
# 编辑 backend/.env 把 VECTOR_STORE_BACKEND=milvus 改为 VECTOR_STORE_BACKEND=chroma

# 重启服务
```

注意：在 Milvus 期间上传的文档不会出现在 Chroma 里，要么重传，要么补一个反向迁移脚本。

## 资源占用参考

Milvus Standalone 三件套（etcd + minio + milvus）：
- 内存：空载 1–2GB，百万级向量 4–8GB
- 磁盘：取决于数据量，每个 768 维向量约 3KB
- 端口：19530（Milvus gRPC）、9091（Milvus HTTP）、9000/9001（MinIO，绑 127.0.0.1）

## 实现要点

- 后端抽象：`backend/app/rag/vector_backend/`
  - `base.py` — `VectorStoreBackend` Protocol
  - `factory.py` — 按 env 选 backend
  - `chroma_backend.py` / `milvus_backend.py` — 两种实现
  - `milvus_filter.py` — Chroma 风格 dict filter → Milvus boolean expression
- 子块镜像：`backend/app/services/child_chunk_service.py` + `backend/app/models/chat_history.py` 的 `ChildChunk` 表
- 写入路径：`ChildChunk.save_batch (注入 chunk_id) → backend.add_documents → ParentChunk → DocumentRecord`；任何一步失败补偿回滚 ChildChunk
- 删除路径：双删（向量库 + MySQL 镜像 + 父块 + 文档记录）
