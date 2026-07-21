# 设计：知识库列表页 + 检索调试页 + 公共顶栏

日期：2026-07-21
状态：已确认，待实现

## 1. 背景与目标

当前 RAG 调试台只有首页上传页（`/`）。两个痛点：
- 关掉浏览器就找不回已建好的知识库（无列表页）。
- 无法直观验证某条 query 召回哪些 chunk、分数如何（无检索调试页）。

在 `rag-center` 一次交付：
- 后端新增 `GET /api/v1/knowledge-bases/tree`，返回 租户 → 知识库 → 文档 三级树。
- 后端小改 `POST /api/v1/rag/retrieve`，在 `metadata` 增加 `latency_ms`（服务端耗时，毫秒）。
- 前端新增 `/knowledge-bases`、`/retrieve` 两个路由，抽出公共顶栏 `AppHeader`，三页共用。
- 调试台不做鉴权、分页、删除。首页上传逻辑保持不变。

## 2. 已确认的决策

- **Git**：直接在 `main` 上开发（用户确认，不新建分支）。
- **AppHeader 职责**：只承载「左侧品牌名 + 右侧导航」。各页面自身的标题/说明文字保留在各页面内容区，不并入 AppHeader。
- **chunk_count**：`Document` 模型无该字段，树接口需实时按 `chunks` 表 `GROUP BY document_id` 统计。
- **shadcn Table**：已存在 `components/ui/table.tsx`，无需补装。

## 3. 后端设计

### 3.1 已核实的现状（约束）

- 响应统一 `ApiResponse[T]`（`app/schemas/common.py`），成功 `ApiResponse.success(data)`；异常由 `main.py` 的 handler 包成 `{code,msg,data:null}`。
- 路由聚合在 `app/api/v1/router.py`，前缀 `/api/v1`；`knowledge_bases.router` 前缀 `/knowledge-bases`。
- DI 工厂在 `app/api/deps.py`（`get_knowledge_base_service` 等）。
- 模型：
  - `knowledge_bases`：`id`(=kb_id), `tenant_id`(index), `name`, `description`, `created_at`, `updated_at`。
  - `documents`：`id`(=document_id), `tenant_id`, `kb_id`(FK), `title`, `source_type`, `status`(int), `created_at`, `updated_at`。`DocumentStatus.SUCCESS=1`。
  - `chunks`：`id`, `tenant_id`, `kb_id`, `document_id`(FK), ...；`Document` 无 chunk_count 列。
- Repo 为 async SQLAlchemy 2.0 `select()` 风格，service 层负责 commit。

### 3.2 新增接口 `GET /api/v1/knowledge-bases/tree?keyword=`

- `keyword` 可选，对 `tenant_id` 做模糊匹配（`ILIKE %keyword%`）。不分页，返回全部。
- 排序：按 `tenant_id` 分组；同租户内知识库按 `created_at` 倒序；文档按 `created_at` 倒序。
- 文档层只返回 `status=SUCCESS` 的记录。
- `chunk_count` 由 `chunks` 表按 `document_id` 聚合计数补齐（无 chunk 的成功文档记 0）。

**响应结构（`data`）**：租户数组，每租户含 `tenant_id` + `knowledge_bases[]`；每 kb 含 `kb_id/name/description/created_at/documents[]`；每 doc 含 `document_id/title/status/chunk_count/created_at`。

**实现落点**：
- `KnowledgeBaseRepository`：新增 `list_all(keyword: str | None) -> list[KnowledgeBase]`（按 tenant_id、created_at 排序）。
- `DocumentRepository`：新增 `list_success_by_kb_ids(kb_ids) -> list[Document]`（`status=SUCCESS`，created_at desc）。
- `ChunkRepository`：新增 `count_by_document_ids(document_ids) -> dict[str,int]`。
- `schemas/knowledge_base.py`：新增 `KnowledgeTreeDoc / KnowledgeTreeKb / KnowledgeTreeTenant`。
- `KnowledgeBaseService`：新增 `get_tree(keyword)`，一次性拉 kb → docs → chunk_count，在内存按 tenant 分组组装（避免 N+1：kb_ids 批量查 docs，document_ids 批量查 chunk_count）。
- `routes/knowledge_bases.py`：新增 `@router.get("/tree", response_model=ApiResponse[list[KnowledgeTreeTenant]])`。

### 3.3 小改 `POST /api/v1/rag/retrieve`

- `RetrieveMetadata` 增加 `latency_ms: int`。
- `RagService.retrieve`：`latency_ms` 已在第 108 行算好，构造 `RetrieveMetadata(...)`（第 157 行）时传入即可。其余逻辑/字段不动。

## 4. 前端设计

### 4.1 已核实的现状

- React18 + Vite + react-router v6（`createBrowserRouter`，`router.tsx`）。
- axios `http`（baseURL `/api`），`unwrap()` 解包 `ApiResponse`。
- shadcn/ui 已装：Button/Card/Input/Label/Textarea/Badge/Table。
- 类型集中在 `types/api.ts`；service 在 `services/`；页面在 `pages/`。

### 4.2 `AppHeader`（`components/app-header.tsx`）

- 左侧固定「RAG 知识文件管理」。
- 右侧用 `useLocation()` 判断当前路由，渲染另两个页面入口（`react-router` `Link`）：
  - `/` → 知识库列表 + 检索调试
  - `/knowledge-bases` → 知识库上传 + 检索调试
  - `/retrieve` → 知识库上传 + 知识库列表
- 三页顶部统一引入；替换首页当前 `<header>`（页面级标题/说明移到 AppHeader 下方各页内容区保留）。

### 4.3 `/knowledge-bases`（`pages/knowledge-file-tree.tsx`，`KnowledgeFileTreePage`）

- 顶部 keyword 搜索框，过滤 `tenant_id`，调用 `knowledgeBaseService.fetchTree(keyword?)`。
- 三级可展开表格，展开/收起用本地 `state`（`Set<string>`），不引额外 UI 库。
- 文档层只显示后端已过滤的 SUCCESS 记录。
- kb 行操作：复制 `kb_id`（`navigator.clipboard`）、去上传（`/?tenant_id=&kb_id=`）、去检索（`/retrieve?tenant_id=&kb_id=`）。
- 不用 localStorage。新增 `services/knowledge-base.ts::fetchTree` 与 `types/api.ts` 树形类型。

### 4.4 `/retrieve`（`pages/retrieve.tsx`，`RetrievePage`）

- 从列表页跳转时读 URL query 预填 `tenant_id/kb_id`。`user_id` 固定 `debug_user`（不展示）。
- 三块 Card：
  1. **检索配置**（可折叠，默认展开）：检索范围（tenant_id/kb_id）+ 检索参数（top_k、mode 三选 vector/bm25/hybrid、hybrid 子参数 vector_top_k/bm25_top_k/rrf_k 仅 hybrid 时同一行显示、rerank 开关 + top_n）。
  2. **检索与召回**：query 多行输入 + 检索按钮 + 召回结果列表（score/vector/bm25/rerank 分数与 rank、title/document_id/chunk_id、content 可折叠）。
  3. **运行摘要**（只读）：`metadata.latency_ms`（标注服务端耗时）、mode、count（vector/bm25/fused）、degraded、rerank 模型名。
- 表单默认值：`top_k=5, mode=hybrid, vector_top_k=20, bm25_top_k=20, rrf_k=60`，rerank 默认启用、top_n=5。
- 请求映射：`top_k` 顶层；`retrieval_options{mode,vector_top_k,bm25_top_k,rrf_k}`；启用 rerank 才传 `rerank_options{enabled,top_n}`，未启用不传该字段。
- 布局：选项名宽 100px 右对齐，标签与控件同行。
- 新增 `services/rag.ts::retrieve`、`types/api.ts` retrieve 请求/响应类型（含 metadata 全字段）。

### 4.5 首页 `/`（`pages/knowledge-upload.tsx`）

- 引入 `AppHeader`；读取 URL query 预填 `tenant_id/kb_id`（当前未读，需补）。
- 上传/建库主逻辑保持不变。

### 4.6 路由（`router.tsx`）

新增 `/knowledge-bases`、`/retrieve` 两条；保留 `*` → `/`。

## 5. 验收标准

对应原始需求第六节全部条目：树形展示正确、文档层仅 SUCCESS、keyword 过滤有效、去上传/去检索预填、检索召回展示、hybrid 子参数条件显示且同行、rerank 开关联动且禁用不传 `rerank_options`、运行摘要展示服务端 `latency_ms`、AppHeader 三页导航按路由切换、首页上传逻辑不变。

## 6. 明确不做（YAGNI）

鉴权、分页、删除、localStorage 持久化、暗色模式、额外 UI 库、`Document.chunk_count` 落库。
