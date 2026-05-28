# LangChain RAG FastAPI Service

一个移动端优先的企业知识库问答系统，前端使用 Vue 3 + Vant，后端由 FastAPI RAG 服务和 Django 用户服务组成。项目支持用户登录、会话持久化、知识库管理、文档上传、向量检索、BM25 混合检索、重排序和流式 AI 问答。

当前项目更像一个完整的“知识库 + AI 问答”应用，而不是单纯的 LangChain demo：用户可以登录后创建或访问知识库，上传文档，在 AI 问答页基于个人或共享知识进行追问，并在会话页管理历史对话。

## 目录

- [核心能力](#核心能力)
- [系统架构](#系统架构)
- [技术栈](#技术栈)
- [项目结构](#项目结构)
- [环境要求](#环境要求)
- [配置说明](#配置说明)
- [本地启动](#本地启动)
- [页面入口](#页面入口)
- [API 速览](#api-速览)
- [RAG 与知识库机制](#rag-与知识库机制)
- [测试与构建](#测试与构建)
- [常见问题](#常见问题)
- [相关文档](#相关文档)

## 核心能力

- AI 问答：支持普通 RAG 查询和 Agent 流式问答，回答可携带来源引用。
- 会话管理：FastAPI 侧将会话和消息持久化到 MySQL，前端提供会话列表、切换和删除。
- 知识库管理：支持个人、部门、公司范围的知识库，并提供成员权限模型。
- 文档管理：支持 `txt`、`pdf`、`md`、`docx`、`pptx` 文件上传、去重、记录、删除和检索。
- 混合检索：向量检索 + BM25 关键词检索，兼顾语义召回和精确词匹配。
- 父子分块：小块用于召回，大块用于给 LLM 提供完整上下文。
- 重排序：默认使用 Qwen3-Reranker-0.6B 对召回文档精排，也支持阿里云重排序配置。
- 多向量后端：默认 ChromaDB，本地需要独立向量服务时可切换 Milvus。
- 用户服务：Django 提供注册、登录、JWT、用户资料、管理员账号管理和文件上传接口。
- 移动端 UI：底部 Tab 覆盖 AI 问答、会话、知识库、我的四个主入口。

## 系统架构

```mermaid
flowchart TD
    subgraph Frontend["Vue 3 + Vite + Vant，端口 3000"]
        A["AI 问答 /aichat"]
        B["会话管理 /sessions"]
        C["知识库 /knowledge"]
        D["我的 /my"]
        E["登录注册 /login /register"]
    end

    subgraph Gateway["Vite 开发代理"]
        P1["/api -> FastAPI 8000"]
        P2["/user、/file -> Django 8001"]
    end

    subgraph FastAPI["FastAPI RAG 服务，端口 8000"]
        F1["Agent / 流式问答"]
        F2["RAG 查询"]
        F3["会话与消息"]
        F4["知识库与文档管理"]
        F5["限流中间件"]
    end

    subgraph RAG["RAG 核心"]
        R1["SmartTextSplitter"]
        R2["Parent / Child Chunks"]
        R3["ChromaDB 或 Milvus"]
        R4["BM25 + 向量混合检索"]
        R5["Qwen3 Reranker"]
    end

    subgraph UserService["Django 用户服务，端口 8001"]
        U1["注册 / 登录 / JWT"]
        U2["用户资料"]
        U3["管理员账号管理"]
        U4["文件上传"]
    end

    subgraph Storage["存储与依赖"]
        S1["MySQL：会话、消息、知识库、文档元数据"]
        S2["Redis：限流、缓存、Token 黑名单"]
        S3["Ollama 或阿里云百炼"]
        S4["本地模型目录：Reranker"]
    end

    A & B & C & D & E --> Gateway
    Gateway --> P1 --> FastAPI
    Gateway --> P2 --> UserService
    FastAPI --> RAG
    FastAPI --> UserService
    FastAPI --> Storage
    UserService --> Storage
```

## 技术栈

| 模块 | 技术 |
| --- | --- |
| 前端 | Vue 3、Vite 7、Vant 4、Vue Router、Pinia、vue-i18n、axios、marked、highlight.js、DOMPurify |
| RAG 后端 | FastAPI、LangChain、LangChain Community、LangChain Chroma、LangChain Milvus、SQLAlchemy、Pydantic、Redis |
| 用户服务 | Django 5.2、Django REST framework、Simple JWT、drf-yasg、Celery、django-redis |
| 向量与检索 | ChromaDB、Milvus、BM25、jieba、sentence-transformers、Qwen3-Reranker-0.6B |
| 模型服务 | 阿里云百炼 Qwen、Ollama、本地 reranker 模型 |
| 数据存储 | MySQL、Redis、本地 ChromaDB 文件、Milvus Docker Compose |

## 项目结构

```text
.
├── backend/                         # FastAPI RAG 服务
│   ├── app/
│   │   ├── agent/                   # LangChain Agent、工具和中间件
│   │   ├── cache/                   # Redis 缓存装饰器
│   │   ├── config/                  # rag/chroma/milvus/agent/prompt 配置
│   │   ├── core/                    # 响应、限流、日志、异常处理
│   │   ├── db/                      # MySQL / Redis 初始化
│   │   ├── models/                  # 会话、消息、知识库、文档、分块表
│   │   ├── rag/                     # 检索、向量后端、重排序、切片
│   │   ├── router/                  # FastAPI 路由
│   │   ├── scheduler/               # 可选的目录监听导入任务
│   │   └── services/                # 会话、知识库、文档、父子块服务
│   ├── tests/                       # 后端测试
│   ├── main.py                      # FastAPI 入口
│   ├── pyproject.toml
│   └── .env.example
├── DjangoUserService/               # Django 用户服务
│   ├── apps/user/                   # 注册、登录、JWT、用户资料、管理员接口
│   ├── apps/file/                   # 文件上传接口
│   ├── DjangoUserService/           # Django settings / urls / celery
│   ├── manage.py
│   ├── pyproject.toml
│   └── .env.example
├── front/                           # Vue 3 移动端前端
│   ├── src/views/                   # AIChat、Sessions、KnowledgeBase、My 等页面
│   ├── src/components/              # TabBar 等公共组件
│   ├── src/config/api.js            # 前端 API 端点
│   ├── src/router/index.js          # 页面路由
│   ├── src/store/                   # Pinia store
│   └── vite.config.js               # Vite 代理配置
├── docs/                            # Milvus、模型、排障等文档
├── docker-compose.milvus.yml        # 可选 Milvus 单机栈
└── README.md
```

## 环境要求

| 依赖 | 建议版本 | 说明 |
| --- | --- | --- |
| Windows + PowerShell | 当前本地开发环境 | 项目已有大量 Windows 启动约定 |
| Python | backend >= 3.12；DjangoUserService >= 3.10 | 两个 Python 服务各自维护虚拟环境 |
| uv | 最新版 | Python 依赖管理 |
| Node.js | 20.19+ 或 22.12+ | Vite 7 的运行要求 |
| MySQL | 8.x 推荐 | Django 5.2 推荐 MySQL 8.0.11+；FastAPI 也使用 MySQL 兼容库 |
| Redis | 7.x 推荐 | 限流、缓存和 Token 黑名单 |
| Docker Desktop | 可选 | 用于 Redis、MySQL、Milvus 等容器化依赖 |
| Ollama | 可选但推荐 | 本地 embedding 或本地聊天模型 |
| 阿里云百炼 API Key | 可选 | 使用 Qwen 云端模型时需要 |

## 配置说明

### FastAPI 后端环境变量

在 `backend/.env` 中配置。下面是常用项，真实密钥不要提交到仓库：

```env
# LLM：ALIYUN 或 OLLAMA
LLM_TYPE=ALIYUN
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL_NAME=qwen3.5:0.8b
ALIYUN_ACCESS_KEY_SECRET=your_api_key
ALIYUN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
CHAT_MODEL_NAME=qwen3-max

# Embedding：OLLAMA 或 ALIYUN
EMBED_MODEL_TYPE=OLLAMA
TEXT_EMBEDDING_MODEL_NAME=qwen3-embedding:0.6b
ALIYUN_EMBED_MODEL_NAME=qwen3-embedding

# MySQL
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DATABASE=chat_history

# Redis
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_DB=0

# 向量后端：chroma 或 milvus
VECTOR_STORE_BACKEND=chroma
MILVUS_HOST=127.0.0.1
MILVUS_PORT=19530

# Django 用户服务
DJANGO_API_URL=http://127.0.0.1:8001

# Reranker
RERANKER_TYPE=LOCAL
RERANKER_MODEL_PATH=D:\Hugging_Face\models\Qwen3-Reranker-0.6B

# JWT：必须和 DjangoUserService/.env 的 JWT_SECRET_KEY 一致
SECRET_KEY=change_me
ALGORITHM=HS256

# 可选：目录监听导入
SCHEDULER_ENABLED=false
SCHEDULER_WATCH_DIR=data/watch
SCHEDULER_INTERVAL_MINUTES=10
```

### Django 用户服务环境变量

在 `DjangoUserService/.env` 中配置：

```env
JWT_SECRET_KEY=change_me

DB_NAME=user_service
DB_USER=root
DB_PASSWORD=your_password
DB_HOST=127.0.0.1
DB_PORT=3306

CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/0
REDIS_CACHE_URL=redis://127.0.0.1:6379/1
```

注意：

- `SECRET_KEY` 和 `JWT_SECRET_KEY` 必须保持一致，否则 FastAPI 无法校验 Django 签发的 JWT。
- Windows 本地建议把 `localhost` 写成 `127.0.0.1`，避免 IPv6 回退导致接口或数据库请求变慢。
- 使用 Milvus 时先启动 `docker-compose.milvus.yml`，并把 `VECTOR_STORE_BACKEND=milvus`。

## 本地启动

以下命令以 PowerShell 为例。

### 1. 安装依赖

```powershell
cd backend
uv sync

cd ..\DjangoUserService
uv sync

cd ..\front
npm install
```

### 2. 启动基础依赖

MySQL 需要提前创建两个数据库，名称可以按 `.env` 调整：

```sql
CREATE DATABASE chat_history CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE user_service CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Redis 可以用 Docker 启动：

```powershell
docker run -d --name redis-rag -p 6379:6379 redis:alpine
```

如果使用 Ollama embedding：

```powershell
ollama serve
ollama pull qwen3-embedding:0.6b
```

如果使用 Milvus：

```powershell
docker compose -f docker-compose.milvus.yml up -d
```

### 3. 初始化 Django 数据库

```powershell
cd DjangoUserService
.\.venv\Scripts\python.exe manage.py migrate
```

### 4. 启动三个应用服务

Django 用户服务：

```powershell
cd DjangoUserService
cmd /c "set HTTP_PROXY=& set HTTPS_PROXY=& set http_proxy=& set https_proxy=& .\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8001"
```

FastAPI RAG 服务：

```powershell
cd backend
cmd /c "set HTTP_PROXY=& set HTTPS_PROXY=& set http_proxy=& set https_proxy=& .\.venv\Scripts\uvicorn.exe main:app --host 127.0.0.1 --port 8000 --reload"
```

Vue 前端：

```powershell
cd front
npm run dev -- --host 127.0.0.1
```

### 5. 访问地址

| 服务 | 地址 |
| --- | --- |
| 前端应用 | `http://127.0.0.1:3000` |
| FastAPI 文档 | `http://127.0.0.1:8000/docs` |
| Django Swagger | `http://127.0.0.1:8001/docs/` |
| Django ReDoc | `http://127.0.0.1:8001/redoc/` |

## 页面入口

| 页面 | 路由 | 说明 |
| --- | --- | --- |
| AI 问答 | `/aichat`、`/aichat/:sessionId` | 新对话、历史会话追问、流式回答、Markdown 渲染 |
| 会话管理 | `/sessions` | 查看、进入和删除历史会话 |
| 知识库 | `/knowledge` | 创建知识库、查看文档、上传文档、触发知识库问答 |
| 我的 | `/my` | 用户信息、设置、账号管理入口 |
| 登录 / 注册 | `/login`、`/register` | 用户认证 |
| 个人资料 | `/profile` | 用户资料维护 |
| 设置 | `/settings` | 偏好设置 |
| 账号管理 | `/admin/accounts` | 管理员用户管理 |

## API 速览

### FastAPI RAG 服务

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/agent/query/stream` | Agent 流式问答 |
| `POST` | `/api/rag/query` | 普通 RAG 查询 |
| `GET` | `/api/session/{session_id}` | 获取单个会话历史 |
| `DELETE` | `/api/session/{session_id}` | 删除会话 |
| `GET` | `/api/sessions` | 获取当前用户会话 |
| `POST` | `/api/vector/add/single` | 上传单个文档到个人知识 |
| `POST` | `/api/vector/add/multiple` | 批量上传文档 |
| `GET` | `/api/vector/list` | 查看个人文档 |
| `DELETE` | `/api/vector/document/{doc_id}` | 删除文档 |
| `DELETE` | `/api/vector/clean` | 清空个人文档 |
| `POST` | `/api/kb` | 创建知识库 |
| `GET` | `/api/kb/list` | 查看可访问知识库 |
| `PATCH` | `/api/kb/{kb_id}` | 更新知识库 |
| `DELETE` | `/api/kb/{kb_id}` | 删除知识库 |
| `POST` | `/api/kb/{kb_id}/documents` | 上传文档到知识库 |
| `GET` | `/api/kb/{kb_id}/documents` | 查看知识库文档 |
| `POST` | `/api/kb/{kb_id}/query` | 在指定知识库内问答 |

### Django 用户服务

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/user/register/` | 注册 |
| `POST` | `/user/login/` | 登录并签发 JWT |
| `POST` | `/user/logout/` | 登出并加入 Token 黑名单 |
| `POST` | `/user/refresh-token/` | 刷新 Token |
| `GET` | `/user/detail/` | 获取当前用户信息 |
| `PUT/PATCH` | `/user/update/` | 更新用户资料 |
| `GET` | `/user/list/` | 管理员获取用户列表 |
| `PATCH` | `/user/{uuid}/set-admin/` | 设置管理员权限 |
| `POST` | `/file/upload/` | 文件上传 |

## RAG 与知识库机制

### 向量后端

通过 `VECTOR_STORE_BACKEND` 选择后端：

- `chroma`：默认嵌入式模式，数据保存在 `backend/data/chromadb`。
- `milvus`：独立向量服务，依赖 `docker-compose.milvus.yml` 中的 etcd、MinIO、Milvus。

### 文档处理

1. 上传文件后写入文档记录表，记录 `doc_id`、`user_id`、`kb_id`、文件名、MD5、大小和分块数。
2. 文本按语言智能分块，生成父块和子块。
3. 子块写入向量库，同时保存到 MySQL，供 BM25 构建索引。
4. 同名或相同 MD5 的文档按用户和知识库范围隔离，避免跨用户误判。

### 检索流程

1. 根据用户和知识库权限过滤可访问内容。
2. 向量检索召回语义相似子块。
3. BM25 召回关键词相关子块。
4. 合并召回结果并映射到父块上下文。
5. 使用 reranker 精排。
6. 将上下文交给 LLM 生成回答，并返回引用来源。

### 知识库权限

知识库支持 `personal`、`dept`、`company` 范围。成员权限分为：

- `viewer`：可检索。
- `editor`：可上传和删除文档。
- `admin`：可管理成员和删除知识库。

## 测试与构建

前端生产构建：

```powershell
cd front
npm run build
```

后端测试：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
```

Django 基础检查：

```powershell
cd DjangoUserService
.\.venv\Scripts\python.exe manage.py check
```

常用烟测：

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:3000/" -UseBasicParsing
Invoke-WebRequest -Uri "http://127.0.0.1:8000/" -UseBasicParsing
Invoke-WebRequest -Uri "http://127.0.0.1:8001/docs/" -UseBasicParsing
```

## 常见问题

### 前端改了但浏览器没变化

优先检查 3000 端口的 Vite 进程路径。它必须指向当前要调试的项目 `front` 目录。路径错了就停掉旧进程，从正确目录重新启动。

### FastAPI 调 Django 超时

本机代理可能拦截了 `127.0.0.1` 请求。启动 Django 和 FastAPI 时清空代理变量：

```powershell
cmd /c "set HTTP_PROXY=& set HTTPS_PROXY=& set http_proxy=& set https_proxy=& <启动命令>"
```

### Django 或数据库操作很慢

Windows 下 `localhost` 可能先走 IPv6 再回退，建议 `.env` 中统一使用 `127.0.0.1`。

### 知识库接口返回 401

需要先登录并让前端携带 `Authorization: Bearer <token>`。FastAPI 会调用 Django `/user/detail/` 校验用户身份。

### Redis 连接失败

确认 6379 端口已启动：

```powershell
docker start redis-rag
```

### Reranker 首次启动慢

首次启动会检查或下载 Qwen3-Reranker-0.6B。确认 `RERANKER_MODEL_PATH` 指向可写且空间充足的目录。

### Vite build 提示 chunk 超过 500 kB

当前 AI 问答页依赖 Markdown、高亮、净化和聊天渲染逻辑，生产构建可能出现 chunk size warning。这是性能优化提示，不代表构建失败。

## 相关文档

- [FastAPI API 文档](./backend/api.md)
- [Django 用户服务 API](./DjangoUserService/api.md)
- [前端 API 说明](./front/api.md)
- [ModelScope 模型说明](./docs/modelscope_model.md)
- [Milvus 迁移说明](./docs/migrate-to-milvus.md)
- [故障排除](./docs/troubleshooting.md)
