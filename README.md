# RAG 中台 (rag-center)

一个 **RAG 能力中台** 后端服务——面向业务方统一提供检索增强生成（Retrieval-Augmented
Generation）的基础能力（知识库、文档索引、检索增强），并将这些能力封装在稳定的 HTTP API 之后。

本仓库是 **第一阶段（stage 1）**：一个结构清晰、可直接运行的骨架，实现最小可运行闭环。
它刻意保持接口面很小（只有 3 个接口），但内部结构和抽象经过设计，后续能力可以平滑加入而无需重写。

> 📖 新租户接入请看 [租户接入指南](docs/tenant-onboarding.md)：开通、API Key、套餐三档、
> retrieve profile 四档与 curl 示例、常见错误码。

> 📊 离线测评：[eval/ 目录](#离线测评)

---

## 项目定位


- 为多个业务线（租户）提供 **统一的一套 RAG 服务**。
- 第一阶段只实现最小的端到端闭环：
  1. 创建知识库
  2. 上传文档并 **同步** 完成索引（切片 → embedding → 写入 pgvector）
  3. 基于知识库返回检索增强的上下文（返回结构化 chunk，**不生成**最终答案）
- 本服务 **不调用** 生成模型。业务方拿到返回的上下文后，自行编排自己的大模型 / 业务逻辑。

## 技术栈

| 关注点 | 选型 |
|---|---|
| 语言 | Python 3.11 |
| Web 框架 | FastAPI |
| 数据库 | PostgreSQL 16 |
| 向量存储 | pgvector 16（使用 `pgvector/pgvector:pg16` 镜像） |
| ORM / 数据库访问 | SQLAlchemy 2.x（异步，`psycopg` 驱动） |
| 数据库迁移 | Alembic |
| 参数校验 / 序列化 | Pydantic v2 |
| Embedding | OpenAI 兼容的 Embedding Provider |

> 文档索引已改为 **Celery 异步执行**：上传接口只建 PROCESSING 记录并投递任务后立即返回，
> 真正的切片、embedding、双写由后台 Worker 完成。需要 Redis 作为 Celery Broker。
>
> 启动 Worker：
> ```bash
> celery -A app.celery_app worker --loglevel=info
> ```

## 目录结构

```
rag-center/
  app/
    api/v1/routes/        # 仅 HTTP 层（请求/响应）。3 个接口。
      knowledge_bases.py
      documents.py
      rag.py
    api/v1/router.py
    api/deps.py           # FastAPI 依赖装配（db、providers、services）
    core/                 # 配置、日志、异常
    db/                   # SQLAlchemy 引擎/会话 + 声明式 Base
    models/               # ORM 模型：KnowledgeBase、Document、Chunk、RetrievalLog
    schemas/              # Pydantic 请求/响应模型 + 统一响应外壳
    services/             # 业务编排
      knowledge_base_service.py
      document_service.py
      rag_service.py
      indexing_service.py # 切片 + embedding + 索引（当前同步，已为异步预留）
    repositories/         # 仅负责数据库读写
    providers/            # 外部系统适配器（可替换）
      embedding/          # EmbeddingProvider 抽象 + OpenAI 兼容实现
      vectorstores/       # VectorStore 抽象 + PgVectorStore 实现
      parsers/            # DocumentParser 抽象 + 纯文本实现
    utils/                # id_generator（UUID）、text_splitter
    main.py
  migrations/             # Alembic
  tests/
  docker-compose.yml
  Dockerfile
  pyproject.toml
  alembic.ini
  .env.example
  README.md
```

**分层规则**

- **API 层**：只处理 HTTP 入参和出参。不做数据库操作，不调用 embedding。
- **Service 层**：业务编排。
- **Repository 层**：数据库读写。
- **Provider 层**：把外部模型和向量库封装在抽象接口之后。
- `IndexingService` 承接同步的 切片 → embedding → 索引 流程，是后续迁移到
  `BackgroundTasks` / Celery / 消息队列的唯一改造点。

## 三个接口（仅第一阶段）

所有响应使用统一外壳：

```json
{ "code": 0, "msg": "success", "data": {} }
```

`code == 0` 表示成功；`code != 0` 表示失败，`msg` 携带可读的原因。

### 1. 创建知识库 — `POST /api/v1/knowledge-bases/create`

```json
{ "name": "退款政策知识库", "description": "用于客服退款问题问答", "tenant_id": "tenant_demo" }
```

### 2. 上传文档 — `POST /api/v1/documents/upload`

```json
{ "tenant_id": "tenant_demo", "kb_id": "kb_xxx", "title": "退款政策", "content": "用户可在订单完成后 7 天内申请退款..." }
```

同步创建文档、切片、embedding、写入 pgvector，成功返回 `status = 1`（SUCCESS）及 `chunk_count`。
失败时文档状态置为 `2`（FAILED）。`3`（PROCESSING）为后续异步索引预留。

### 3. 检索增强 — `POST /api/v1/rag/retrieve`

```json
{ "tenant_id": "tenant_demo", "kb_id": "kb_xxx", "user_id": "user_demo", "query": "退款需要几天内申请？" }
```

返回 top-k 召回的 chunk（含 `document_id`、`chunk_id`、`title`、`content`、`score`）以及
元信息（`top_k`、`vector_store`、`retrieval`、`rerank`）。**不返回** 拼接后的 `context_text`，也 **不生成** 答案。

> 当前版本支持三种检索模式：
> - **`vector`**（默认）：纯向量相似度召回（pgvector）
> - **`bm25`**：纯 BM25 关键词召回（Elasticsearch）
> - **`hybrid`**：向量 + BM25 并行召回，RRF 融合排序
>
> 以及可选的 **LLM 重排（rerank）**：召回后可把候选 chunk 交给大模型打分，
> 再按 `rerank_score` 重新排序并返回 `top_n` 个结果。rerank 和 BM25 失败会自动
> 降级，不影响接口整体可用性。

#### 混合检索请求示例（hybrid mode + rerank）

```json
{
  "tenant_id": "tenant_demo",
  "kb_id": "kb_xxx",
  "user_id": "user_demo",
  "query": "退款需要几天内申请？",
  "top_k": 20,
  "retrieval_options": {
    "mode": "hybrid",
    "vector_top_k": 20,
    "bm25_top_k": 20,
    "rrf_k": 60
  },
  "rerank_options": {
    "enabled": true,
    "top_n": 5
  }
}
```

#### 启用混合检索 + rerank 后的响应片段

```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "query": "退款需要几天内申请？",
    "kb_id": "kb_xxx",
    "retrieved_chunks": [
      {
        "document_id": "doc_001",
        "chunk_id": "chunk_001",
        "title": "退款政策",
        "content": "用户可在订单完成后 7 天内申请退款。",
        "score": 0.0321,
        "vector_score": 0.86,
        "bm25_score": 12.4,
        "vector_rank": 1,
        "bm25_rank": 2,
        "retrieval_source": "hybrid",
        "rerank_score": 0.95
      }
    ],
    "metadata": {
      "top_k": 20,
      "vector_store": "pgvector",
      "retrieval": {
        "mode": "hybrid",
        "fusion": "rrf",
        "rrf_k": 60,
        "vector_store": "pgvector",
        "keyword_search": "elasticsearch",
        "vector_top_k": 20,
        "bm25_top_k": 20,
        "vector_count": 20,
        "bm25_count": 18,
        "fused_count": 31,
        "degraded": false
      },
      "rerank": {
        "enabled": true,
        "provider": "llm",
        "llm_provider": "openai_compatible",
        "model": "deepseek-chat",
        "top_n": 5,
        "degraded": false
      }
    }
  }
}
```

### 混合检索（Hybrid Search）+ RRF 融合设计

当前 RAG 链路（`hybrid` 模式）：

```text
query
  -> query embedding
  -> pgvector 向量召回 vector_top_k + Elasticsearch BM25 召回 bm25_top_k（并行）
  -> RRF（Reciprocal Rank Fusion）融合排序
  -> 得到候选 chunks（按 fused_score 排序）
  -> （可选）LLM rerank
  -> 返回最终 chunks
```

#### 为什么使用 RRF

不直接加权融合 `vector_score * 0.6 + bm25_score * 0.4` 的原因：

- 向量分数和 BM25 分数不是同一量纲（向量相似度通常 0~1，BM25 分数无上界）
- BM25 分数受词频、字段长度、语料分布影响，直接相加不稳定
- 需要额外归一化，工程复杂度高

**RRF（Reciprocal Rank Fusion）**只看排名，不依赖原始分数尺度：

```
rrf_score = 1 / (rrf_k + rank)
```

如果一个 chunk 同时被向量检索和 BM25 召回：

```
fused_score = 1 / (rrf_k + vector_rank) + 1 / (rrf_k + bm25_rank)
```

- `rrf_k` 默认 60（可通过 `HYBRID_RRF_K` 配置）
- 实现简单，工程上稳定，适合作为第一版混合检索默认策略

#### 失败降级策略

- `RETRIEVAL_MODE=vector`：完全不依赖 Elasticsearch
- `RETRIEVAL_MODE=hybrid`：
  - pgvector 检索失败 → 接口失败（主链路）
  - ES BM25 检索失败 → **接口不失败**，自动降级为纯向量结果，`metadata.retrieval.degraded=true` 并带 `degraded_reason`
- rerank 失败 → 接口不失败，降级为原向量/混合排序，`metadata.rerank.degraded=true`

### 可选 rerank 请求示例（纯向量模式）

```json
{
  "tenant_id": "tenant_demo",
  "kb_id": "kb_xxx",
  "user_id": "user_demo",
  "query": "退款需要几天内申请？",
  "top_k": 20,
  "rerank_options": {
    "enabled": true,
    "top_n": 5
  }
}
```

#### 启用 rerank 后的响应片段

```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "query": "退款需要几天内申请？",
    "kb_id": "kb_xxx",
    "retrieved_chunks": [
      {
        "document_id": "doc_001",
        "chunk_id": "chunk_001",
        "title": "退款政策",
        "content": "用户可在订单完成后 7 天内申请退款。",
        "score": 0.86,
        "rerank_score": 0.95
      }
    ],
    "metadata": {
      "top_k": 20,
      "vector_store": "pgvector",
      "rerank": {
        "enabled": true,
        "provider": "llm",
        "llm_provider": "openai_compatible",
        "model": "deepseek-chat",
        "top_n": 5,
        "candidate_count": 20,
        "degraded": false,
        "error": null
      }
    }
  }
}
```

### LLM 重排（rerank）设计

当前 RAG 链路：

```text
query
  -> query embedding
  -> VectorStore.similarity_search 召回 candidate chunks
  -> （可选）RerankProvider.rerank(query, candidates, top_n)
  -> 返回结构化 retrieved_chunks
```

#### 分层设计

为避免把具体模型厂商写死，代码分成两层抽象：

- **`LLMProvider`**：统一大模型调用接口，负责 `chat_json()`。
  - 第一版实现：`OpenAICompatibleLLMProvider`
  - 任何兼容 OpenAI chat completions 协议的厂商（DeepSeek、百炼等）都走这里。
- **`RerankProvider`**：统一重排接口。
  - `LLMRerankProvider`：依赖 `LLMProvider.chat_json()` 做打分重排。
  - `NoopRerankProvider`：不重排，占位实现，用于关闭 rerank 或做对照测试。

这样以后如果新增：
- `AzureOpenAILLMProvider`
- `ClaudeCompatibleLLMProvider`
- `CrossEncoderRerankProvider`

都不需要修改 `RAGService` 的主流程。

#### 候选数据如何传给大模型

传给大模型的是**结构化 JSON**，而不是随意拼接的一大段文本：

```json
{
  "query": "退款需要几天内申请？",
  "candidates": [
    {
      "chunk_id": "chunk_001",
      "document_id": "doc_001",
      "title": "退款政策",
      "content": "用户可在订单完成后 7 天内申请退款。",
      "vector_score": 0.86
    }
  ],
  "top_n": 5
}
```

为了控制 token 成本：
- 单次 rerank 的候选 chunk 数由 `RERANK_MAX_CANDIDATES` 控制（默认 20）
- 单个 chunk 的 `content` 会截断到 `RERANK_CHUNK_MAX_CHARS`（默认 1000）
- 不传 embedding 向量本身，也不传数据库内部无关字段

#### 失败降级策略

- **embedding 失败 / 向量检索失败**：接口失败（这是主链路）
- **rerank 失败**：接口**不失败**，自动降级为原始向量排序
  - `metadata.rerank.degraded = true`
  - `metadata.rerank.error` 带简要错误原因
  - `retrieved_chunks` 仍返回原始向量召回结果

## 本地启动

### 方式 A —— Docker Compose（推荐）

```bash
cp .env.example .env          # 配置 MODEL_API_KEY / MODEL_BASE_URL 用于 embedding
docker compose up --build
```

会启动 PostgreSQL+pgvector，执行 `alembic upgrade head`，并在 `http://localhost:8000` 提供 API。

### 方式 B —— 本地运行，数据库用 Docker

```bash
# 1. 只启动数据库
docker compose up -d postgres

# 2. 安装依赖（Python 3.11）
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 3. 配置环境变量
cp .env.example .env          # DATABASE_URL 已指向 localhost:5432

# 4. 执行迁移，然后运行
alembic upgrade head
uvicorn app.main:app --reload
```

## Alembic 迁移步骤

```bash
# 应用全部迁移（创建 vector 扩展 + 核心表）
alembic upgrade head

# 修改模型后自动生成新的迁移
alembic revision --autogenerate -m "描述本次变更"

# 回滚一步
alembic downgrade -1
```

数据库地址从环境变量 `DATABASE_URL` 读取（见 `migrations/env.py`），不写死在 `alembic.ini` 里。

## 快速冒烟测试

```bash
# 1. 创建知识库
curl -s localhost:8000/api/v1/knowledge-bases/create \
  -H 'content-type: application/json' \
  -d '{"name":"退款政策知识库","description":"客服退款","tenant_id":"tenant_demo"}'

# 2. 上传文档（使用上一步返回的 kb_id）
curl -s localhost:8000/api/v1/documents/upload \
  -H 'content-type: application/json' \
  -d '{"tenant_id":"tenant_demo","kb_id":"<kb_id>","title":"退款政策","content":"用户可在订单完成后 7 天内申请退款。"}'

# 3. 检索
curl -s localhost:8000/api/v1/rag/retrieve \
  -H 'content-type: application/json' \
  -d '{"tenant_id":"tenant_demo","kb_id":"<kb_id>","user_id":"user_demo","query":"退款需要几天内申请？"}'
```

## 日志体系

### 输出与文件

- **控制台**：彩色输出，级别高亮。
- **`logs/app.log`**：全量日志，按大小滚动（默认单文件 10MB，保留 10 个）。
- **`logs/error.log`**：**仅 ERROR 及以上**，带完整堆栈，方便快速定位线上问题。

滚动策略、目录、是否落文件均由 `.env` 控制（`LOG_DIR`、`LOG_MAX_BYTES`、
`LOG_BACKUP_COUNT`、`LOG_TO_FILE`、`LOG_REQUEST_BODY`）。

日志采用 `QueueHandler + QueueListener`：业务线程只把日志入队，真正的磁盘/控制台写入在
后台线程完成，**不阻塞业务**；`request_id` 用 `contextvars` 存储，**异步/协程安全**。

### 统一格式

```
时间 | 级别 | 模块:函数:行号 | request_id | 内容
2026-07-20 16:01:11 | INFO  | rag_service:retrieve:88 | a1b2c3d4 | RAG_RETRIEVE | kb_id=... | hits=3 | cost=42ms
```

### 使用示例

```python
from app.core.logging import get_logger, log_api, log_llm_request, log_llm_response

logger = get_logger(__name__)
logger.info("业务关键节点 | order_id=%s", order_id)   # 全局调用

# 1) 接口/函数调用日志装饰器（自动记录入参、返回、耗时；同步/异步通用）
@log_api
async def call_api(...):
    ...

# 2) 大模型交互专用日志
log_llm_request("gpt-4o-mini", prompt)
log_llm_response("gpt-4o-mini", answer, cost_ms=123.4)
```

- **HTTP 请求/响应**：由 `RequestLoggingMiddleware` 自动记录（方法、URL、请求体、响应体、
  状态码、耗时），并为每个请求生成 `request_id` 写入响应头 `X-Request-ID`。
- **系统报错**：全局异常处理器记录完整堆栈、异常类型和上下文（进 `error.log`）。

## 错误码规范

统一响应仍为 `{code, msg, data}`。错误码按区间分类，便于一眼定位问题归属：

| 区间 | 含义 |
|---|---|
| `0` | 成功 |
| `10000~19999` | 通用 / 请求 / 权限 / 资源 |
| `20000~29999` | 接口 / HTTP / 外部请求 |
| `30000~39999` | 数据库 / 存储（含向量库） |
| `40000~49999` | 大模型 LLM 专属（含 embedding） |
| `50000~59999` | 系统 / 服务异常 |

设计原则：**对外只返回安全、简洁的 `msg`；对内的完整上下文（`detail` + 堆栈）只进日志**，
不泄露技术细节。全部错误码见 `app/core/error_codes.py`。

### 使用示例

```python
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException, raise_error, KnowledgeBaseNotFound

# 1) 语义化子类（推荐，可读性好）
raise KnowledgeBaseNotFound(kb_id)          # -> code=10010, msg="知识库不存在"

# 2) 快速抛错工具函数（detail 只进日志，不返回给调用方）
raise_error(ErrorCode.LLM_TIMEOUT, detail=f"model={model} timeout=30s")

# 3) 直接使用统一异常
raise AppException(ErrorCode.DB_ERROR, detail="unique violation on documents.id")
```

抛出的 `AppException` 会被全局处理器捕获，自动转成统一外壳：

```json
{ "code": 10010, "msg": "知识库不存在", "data": null }
```

## 后续扩展方向

以下抽象和改造点已经预留，是规划中的下一步：

- **混合检索**：接入 Elasticsearch / OpenSearch，实现 BM25 + 向量融合。
- **异步索引**：把 `IndexingService.index_document()` 迁移到 `BackgroundTasks`、
  Celery 或消息队列（届时再引入 Redis/Celery）。
- **重排序**：召回后增加 `RerankProvider` 抽象。
- **更多向量库**：在现有 `VectorStore` 接口下增加 `MilvusVectorStore`、
  `QdrantVectorStore`、`ElasticVectorStore`。
- **权限控制**：检索时按 `tenant_id` / `user_id` 做 ACL 过滤。
- **评测与反馈闭环**：评测集、离线指标、反馈采集。
- **管理后台**：知识库与文档的管理界面。

## 第一阶段边界（刻意不实现）

管理后台页面、多种文件格式解析、Elasticsearch/OpenSearch、rerank、复杂权限、评测系统、
A/B 测试、多轮会话记忆、Redis/Celery。以上能力的扩展点都已在代码结构和接口抽象中预留。
