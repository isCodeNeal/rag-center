# 知识库列表页 + 检索调试页 + 公共顶栏 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 rag-center 上新增知识库树形列表页（`/knowledge-bases`）与检索调试页（`/retrieve`），抽出三页共用的 `AppHeader`，并补齐支撑用的后端 tree 接口与 retrieve 耗时字段。

**Architecture:** 后端沿用 FastAPI + async SQLAlchemy 2.0 + Pydantic 的 repository→service→route 分层，新增只读 tree 接口并给 retrieve 响应补 `latency_ms`。前端沿用 React18 + Vite + react-router v6 + shadcn/ui，新增两页与两个 service，抽 `AppHeader`。

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy 2.0 async / Pydantic v2 / pytest-asyncio；React 18 / Vite / react-router-dom 6 / axios / shadcn/ui / Tailwind。

## Global Constraints

- 后端响应统一 `ApiResponse[T]`（`app/schemas/common.py`），成功用 `ApiResponse.success(data)`；异常由 `app/main.py` handler 包成 `{code,msg,data:null}`。
- 所有 repository 方法为 `async`，用 SQLAlchemy 2.0 `select()`；只读查询不 commit。
- `DocumentStatus.SUCCESS == 1`（`app/models/enums.py`）。
- 后端测试：pytest `asyncio_mode = "auto"`；API 层用 `app.dependency_overrides` + fake service；service 层用 fake repo。运行命令 `python -m pytest`（在 `rag-center` 目录下，需先 `pip install -e ".[dev]"`，环境已装 `.venv`）。
- 前端无单元测试框架（不引入，YAGNI）。每个前端任务的验证 = `npm run typecheck`（`tsc -b --noEmit`）通过 + `npm run build` 通过。前端目录为 `rag-center/frontend`。
- axios `http` baseURL 为 `/api`，故 service 里路径写 `/v1/...`；`unwrap()` 解包 `ApiResponse`。
- 前端不使用 localStorage。UI 只用已装 shadcn 组件（Button/Card/Input/Label/Textarea/Badge/Table）。
- Git：直接在 `main` 上开发（用户确认）。每个 Task 末尾 commit。
- 提交信息结尾附：`Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

## 文件结构

**后端（新增/修改）：**
- Modify `app/schemas/rag.py` — `RetrieveMetadata` 增 `latency_ms`
- Modify `app/services/rag_service.py` — 构造 `RetrieveMetadata` 时传 `latency_ms`
- Modify `app/schemas/knowledge_base.py` — 新增 3 个 tree schema
- Modify `app/repositories/knowledge_base_repository.py` — 新增 `list_all`
- Modify `app/repositories/document_repository.py` — 新增 `list_success_by_kb_ids`
- Modify `app/repositories/chunk_repository.py` — 新增 `count_by_document_ids`
- Modify `app/services/knowledge_base_service.py` — 构造函数加两个 repo + `get_tree`
- Modify `app/api/deps.py` — `get_knowledge_base_service` 注入新 repo
- Modify `app/api/v1/routes/knowledge_bases.py` — 新增 `GET /tree`
- Modify `tests/test_rag_service.py`、`tests/test_api.py` — 新增断言/用例

**前端（新增/修改）：**
- Create `frontend/src/components/app-header.tsx`
- Modify `frontend/src/pages/knowledge-upload.tsx` — 用 AppHeader + 读 URL query
- Modify `frontend/src/router.tsx` — 加两条路由
- Modify `frontend/src/types/api.ts` — tree + retrieve 类型
- Modify `frontend/src/services/knowledge-base.ts` — `fetchTree`
- Create `frontend/src/services/rag.ts` — `retrieve`
- Create `frontend/src/pages/knowledge-file-tree.tsx`
- Create `frontend/src/pages/retrieve.tsx`

---

## Task 1: 后端 — retrieve 响应增加 latency_ms

**Files:**
- Modify: `app/schemas/rag.py:40-44`
- Modify: `app/services/rag_service.py:157-162`
- Test: `tests/test_rag_service.py`

**Interfaces:**
- Produces: `RetrieveMetadata.latency_ms: int`（前端 `RetrieveMetadata` 类型、运行摘要依赖）。

- [ ] **Step 1: 在既有测试里加 latency_ms 断言（失败测试）**

在 `tests/test_rag_service.py` 的 `test_rag_service_without_rerank_returns_vector_hits` 末尾（`assert data.metadata.rerank.enabled is False` 之后）追加：

```python
    assert isinstance(data.metadata.latency_ms, int)
    assert data.metadata.latency_ms >= 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_rag_service.py::test_rag_service_without_rerank_returns_vector_hits -v`
Expected: FAIL — `AttributeError`/`ValidationError`，`RetrieveMetadata` 无 `latency_ms`。

- [ ] **Step 3: 给 schema 增加字段**

`app/schemas/rag.py`，把 `RetrieveMetadata` 改为：

```python
class RetrieveMetadata(BaseModel):
    top_k: int
    vector_store: str
    latency_ms: int
    retrieval: RetrievalMetadata
    rerank: RerankMetadata
```

- [ ] **Step 4: service 构造时传入 latency_ms**

`app/services/rag_service.py`，把结尾的 `RetrieveMetadata(...)`（约 157 行）改为：

```python
            metadata=RetrieveMetadata(
                top_k=top_k,
                vector_store=self._vector_store_name,
                latency_ms=latency_ms,
                retrieval=retrieval_meta,
                rerank=rerank_meta,
            ),
```

（`latency_ms` 已在第 108 行 `latency_ms = int((time.perf_counter() - started) * 1000)` 算好，无需新增计时。）

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_rag_service.py -v`
Expected: PASS（3 条全过）。

- [ ] **Step 6: Commit**

```bash
git add app/schemas/rag.py app/services/rag_service.py tests/test_rag_service.py
git commit -m "feat: retrieve 响应 metadata 增加 latency_ms 服务端耗时

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: 后端 — 知识库树形 schema

**Files:**
- Modify: `app/schemas/knowledge_base.py`
- Test: `tests/test_knowledge_tree.py`（新建）

**Interfaces:**
- Produces:
  - `KnowledgeTreeDoc(document_id:str, title:str, status:int, chunk_count:int, created_at:datetime)`
  - `KnowledgeTreeKb(kb_id:str, name:str, description:str|None, created_at:datetime, documents:list[KnowledgeTreeDoc])`
  - `KnowledgeTreeTenant(tenant_id:str, knowledge_bases:list[KnowledgeTreeKb])`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_knowledge_tree.py`：

```python
"""知识库树形 schema 单元测试。"""
from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.knowledge_base import (
    KnowledgeTreeDoc,
    KnowledgeTreeKb,
    KnowledgeTreeTenant,
)


def test_tree_schema_nests_tenant_kb_doc():
    doc = KnowledgeTreeDoc(
        document_id="doc-1",
        title="backend_engineer.md",
        status=1,
        chunk_count=12,
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    kb = KnowledgeTreeKb(
        kb_id="kb-1",
        name="技术岗位知识库",
        description="d",
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        documents=[doc],
    )
    tenant = KnowledgeTreeTenant(tenant_id="tech_position", knowledge_bases=[kb])
    assert tenant.knowledge_bases[0].documents[0].chunk_count == 12
    assert tenant.knowledge_bases[0].description == "d"
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_knowledge_tree.py -v`
Expected: FAIL — `ImportError`，schema 未定义。

- [ ] **Step 3: 实现 schema**

在 `app/schemas/knowledge_base.py` 末尾追加：

```python
class KnowledgeTreeDoc(BaseModel):
    document_id: str
    title: str
    status: int
    chunk_count: int
    created_at: datetime


class KnowledgeTreeKb(BaseModel):
    kb_id: str
    name: str
    description: str | None = None
    created_at: datetime
    documents: list[KnowledgeTreeDoc] = Field(default_factory=list)


class KnowledgeTreeTenant(BaseModel):
    tenant_id: str
    knowledge_bases: list[KnowledgeTreeKb] = Field(default_factory=list)
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_knowledge_tree.py -v`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add app/schemas/knowledge_base.py tests/test_knowledge_tree.py
git commit -m "feat: 知识库树形响应 schema

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: 后端 — 三个 repository 查询方法

**Files:**
- Modify: `app/repositories/knowledge_base_repository.py`
- Modify: `app/repositories/document_repository.py`
- Modify: `app/repositories/chunk_repository.py`

**Interfaces:**
- Produces:
  - `KnowledgeBaseRepository.list_all(keyword: str | None) -> list[KnowledgeBase]`（按 `tenant_id asc, created_at desc` 排序；keyword 非空时 `tenant_id ILIKE %keyword%`）
  - `DocumentRepository.list_success_by_kb_ids(kb_ids: list[str]) -> list[Document]`（`status=SUCCESS`，`created_at desc`；空入参返回 `[]`）
  - `ChunkRepository.count_by_document_ids(document_ids: list[str]) -> dict[str, int]`（空入参返回 `{}`）

> 说明：这三个方法直接依赖真实 DB 连接，纯查询逻辑简单且无单测桩，故本任务不写单元测试；它们的正确性在 Task 4 的 service 层（fake repo 返回固定数据）与 API 层用例中间接覆盖。这是有意为之的取舍，非遗漏。

- [ ] **Step 1: KnowledgeBaseRepository.list_all**

在 `app/repositories/knowledge_base_repository.py` 类内追加方法（文件已 `from sqlalchemy import select`）：

```python
    async def list_all(self, keyword: str | None = None) -> list[KnowledgeBase]:
        stmt = select(KnowledgeBase)
        if keyword:
            stmt = stmt.where(KnowledgeBase.tenant_id.ilike(f"%{keyword}%"))
        stmt = stmt.order_by(
            KnowledgeBase.tenant_id.asc(), KnowledgeBase.created_at.desc()
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
```

- [ ] **Step 2: DocumentRepository.list_success_by_kb_ids**

`app/repositories/document_repository.py`，顶部 import 改为：

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.enums import DocumentStatus
```

类内追加：

```python
    async def list_success_by_kb_ids(self, kb_ids: list[str]) -> list[Document]:
        if not kb_ids:
            return []
        stmt = (
            select(Document)
            .where(
                Document.kb_id.in_(kb_ids),
                Document.status == DocumentStatus.SUCCESS.value,
            )
            .order_by(Document.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
```

- [ ] **Step 3: ChunkRepository.count_by_document_ids**

`app/repositories/chunk_repository.py`，顶部 import 改为 `from sqlalchemy import delete, func, select`，类内追加：

```python
    async def count_by_document_ids(self, document_ids: list[str]) -> dict[str, int]:
        if not document_ids:
            return {}
        stmt = (
            select(Chunk.document_id, func.count().label("cnt"))
            .where(Chunk.document_id.in_(document_ids))
            .group_by(Chunk.document_id)
        )
        result = await self._session.execute(stmt)
        return {document_id: int(cnt) for document_id, cnt in result.all()}
```

- [ ] **Step 4: 静态检查通过**

Run: `python -c "import app.repositories.knowledge_base_repository, app.repositories.document_repository, app.repositories.chunk_repository"`
Expected: 无输出、无异常（模块导入成功）。

- [ ] **Step 5: Commit**

```bash
git add app/repositories/
git commit -m "feat: 知识库/文档/chunk 树形查询 repository 方法

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: 后端 — get_tree service + DI + 路由 + API 测试

**Files:**
- Modify: `app/services/knowledge_base_service.py`
- Modify: `app/api/deps.py:112-115`
- Modify: `app/api/v1/routes/knowledge_bases.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: Task 2 的 tree schema、Task 3 的三个 repo 方法。
- Produces:
  - `KnowledgeBaseService.__init__(session, kb_repository, document_repository, chunk_repository)`
  - `KnowledgeBaseService.get_tree(keyword: str | None) -> list[KnowledgeTreeTenant]`
  - `GET /api/v1/knowledge-bases/tree?keyword=` → `ApiResponse[list[KnowledgeTreeTenant]]`

- [ ] **Step 1: 写失败的 API 测试**

在 `tests/test_api.py` 追加（顶部已 import `datetime, timezone`）：

```python
from app.schemas.knowledge_base import KnowledgeTreeKb, KnowledgeTreeDoc, KnowledgeTreeTenant


class _FakeTreeKBService:
    async def get_tree(self, keyword=None):
        doc = KnowledgeTreeDoc(
            document_id="doc-1",
            title="backend_engineer.md",
            status=1,
            chunk_count=12,
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        kb = KnowledgeTreeKb(
            kb_id="kb-1",
            name="技术岗位知识库",
            description="d",
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            documents=[doc],
        )
        return [KnowledgeTreeTenant(tenant_id="tech_position", knowledge_bases=[kb])]


def test_knowledge_tree_success(client):
    app.dependency_overrides[get_knowledge_base_service] = lambda: _FakeTreeKBService()
    try:
        resp = client.get("/api/v1/knowledge-bases/tree?keyword=tech")
    finally:
        app.dependency_overrides.pop(get_knowledge_base_service, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"][0]["tenant_id"] == "tech_position"
    assert body["data"][0]["knowledge_bases"][0]["kb_id"] == "kb-1"
    assert body["data"][0]["knowledge_bases"][0]["documents"][0]["chunk_count"] == 12
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_api.py::test_knowledge_tree_success -v`
Expected: FAIL — 路由 404（`/tree` 未定义）。

- [ ] **Step 3: 扩展 KnowledgeBaseService**

`app/services/knowledge_base_service.py`，整体替换为：

```python
"""知识库 service。"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.knowledge_base import KnowledgeBase
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.schemas.knowledge_base import (
    CreateKnowledgeBaseRequest,
    KnowledgeBaseData,
    KnowledgeTreeDoc,
    KnowledgeTreeKb,
    KnowledgeTreeTenant,
)
from app.utils.id_generator import new_kb_id

logger = get_logger(__name__)


class KnowledgeBaseService:
    def __init__(
        self,
        session: AsyncSession,
        kb_repository: KnowledgeBaseRepository,
        document_repository: DocumentRepository | None = None,
        chunk_repository: ChunkRepository | None = None,
    ):
        self._session = session
        self._kb_repo = kb_repository
        self._doc_repo = document_repository
        self._chunk_repo = chunk_repository

    async def create(self, req: CreateKnowledgeBaseRequest) -> KnowledgeBaseData:
        kb = KnowledgeBase(
            id=new_kb_id(),
            tenant_id=req.tenant_id,
            name=req.name,
            description=req.description,
        )
        await self._kb_repo.create(kb)
        await self._session.commit()
        await self._session.refresh(kb)
        logger.info("KB_CREATED | kb_id=%s | tenant_id=%s | name=%s", kb.id, kb.tenant_id, kb.name)
        return KnowledgeBaseData(
            kb_id=kb.id,
            name=kb.name,
            tenant_id=kb.tenant_id,
            created_at=kb.created_at,
        )

    async def get_tree(self, keyword: str | None = None) -> list[KnowledgeTreeTenant]:
        kbs = await self._kb_repo.list_all(keyword)
        kb_ids = [kb.id for kb in kbs]
        docs = await self._doc_repo.list_success_by_kb_ids(kb_ids) if kb_ids else []
        doc_ids = [d.id for d in docs]
        counts = await self._chunk_repo.count_by_document_ids(doc_ids) if doc_ids else {}

        # 按 kb_id 分组文档（docs 已按 created_at desc 排序，分组保持该顺序）
        docs_by_kb: dict[str, list[KnowledgeTreeDoc]] = {}
        for d in docs:
            docs_by_kb.setdefault(d.kb_id, []).append(
                KnowledgeTreeDoc(
                    document_id=d.id,
                    title=d.title,
                    status=d.status,
                    chunk_count=counts.get(d.id, 0),
                    created_at=d.created_at,
                )
            )

        # 按 tenant_id 分组知识库（kbs 已按 tenant_id asc, created_at desc 排序）
        tenants: dict[str, KnowledgeTreeTenant] = {}
        for kb in kbs:
            tenant = tenants.get(kb.tenant_id)
            if tenant is None:
                tenant = KnowledgeTreeTenant(tenant_id=kb.tenant_id, knowledge_bases=[])
                tenants[kb.tenant_id] = tenant
            tenant.knowledge_bases.append(
                KnowledgeTreeKb(
                    kb_id=kb.id,
                    name=kb.name,
                    description=kb.description,
                    created_at=kb.created_at,
                    documents=docs_by_kb.get(kb.id, []),
                )
            )
        return list(tenants.values())
```

- [ ] **Step 4: 更新 DI 工厂**

`app/api/deps.py`，顶部 import 处已有 `ChunkRepository`、`DocumentRepository`、`KnowledgeBaseRepository`。把 `get_knowledge_base_service` 改为：

```python
def get_knowledge_base_service(
    db: AsyncSession = Depends(get_db),
) -> KnowledgeBaseService:
    return KnowledgeBaseService(
        db,
        KnowledgeBaseRepository(db),
        DocumentRepository(db),
        ChunkRepository(db),
    )
```

- [ ] **Step 5: 新增路由**

`app/api/v1/routes/knowledge_bases.py`，import 增加 tree schema，追加路由：

```python
from app.schemas.knowledge_base import (
    CreateKnowledgeBaseRequest,
    KnowledgeBaseData,
    KnowledgeTreeTenant,
)
```

```python
@router.get("/tree", response_model=ApiResponse[list[KnowledgeTreeTenant]])
async def get_knowledge_tree(
    keyword: str | None = None,
    service: KnowledgeBaseService = Depends(get_knowledge_base_service),
) -> ApiResponse[list[KnowledgeTreeTenant]]:
    data = await service.get_tree(keyword)
    return ApiResponse.success(data)
```

> 注意：`GET /tree` 是静态路径，与既有 `POST /create` 无冲突。

- [ ] **Step 6: 运行全部后端测试**

Run: `python -m pytest`
Expected: PASS（含新增 `test_knowledge_tree_success` 及既有全部用例）。

- [ ] **Step 7: Commit**

```bash
git add app/services/knowledge_base_service.py app/api/deps.py app/api/v1/routes/knowledge_bases.py tests/test_api.py
git commit -m "feat: 新增 GET /api/v1/knowledge-bases/tree 树形查询接口

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: 前端 — AppHeader 公共顶栏

**Files:**
- Create: `frontend/src/components/app-header.tsx`

**Interfaces:**
- Produces: `AppHeader`（无 props；内部用 `useLocation()` 决定右侧导航）。

- [ ] **Step 1: 创建组件**

`frontend/src/components/app-header.tsx`：

```tsx
import { Link, useLocation } from "react-router-dom";

interface NavLink {
  to: string;
  label: string;
}

// 每个路由下、右侧要展示的“其他页面”入口
const NAV_BY_PATH: Record<string, NavLink[]> = {
  "/": [
    { to: "/knowledge-bases", label: "知识库列表" },
    { to: "/retrieve", label: "检索调试" },
  ],
  "/knowledge-bases": [
    { to: "/", label: "知识库上传" },
    { to: "/retrieve", label: "检索调试" },
  ],
  "/retrieve": [
    { to: "/", label: "知识库上传" },
    { to: "/knowledge-bases", label: "知识库列表" },
  ],
};

export function AppHeader() {
  const { pathname } = useLocation();
  const links = NAV_BY_PATH[pathname] ?? NAV_BY_PATH["/"];

  return (
    <header className="flex items-center justify-between border-b bg-card px-6 py-3">
      <Link to="/" className="text-lg font-bold tracking-tight">
        RAG 知识文件管理
      </Link>
      <nav className="flex items-center gap-4 text-sm">
        {links.map((l) => (
          <Link key={l.to} to={l.to} className="text-muted-foreground hover:text-foreground">
            {l.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
```

- [ ] **Step 2: 类型检查通过**

Run: `cd frontend && npm run typecheck`
Expected: 无类型错误（组件独立，未被引用也应通过）。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/app-header.tsx
git commit -m "feat(fe): 新增 AppHeader 公共顶栏组件

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: 前端 — 路由接线 + 首页接入 AppHeader 与 URL 预填

**Files:**
- Modify: `frontend/src/router.tsx`
- Modify: `frontend/src/pages/knowledge-upload.tsx`
- Create: `frontend/src/pages/knowledge-file-tree.tsx`（本任务先建占位，Task 8 填充）
- Create: `frontend/src/pages/retrieve.tsx`（本任务先建占位，Task 9 填充）

**Interfaces:**
- Consumes: Task 5 的 `AppHeader`。
- Produces: 路由 `/knowledge-bases` → `KnowledgeFileTreePage`；`/retrieve` → `RetrievePage`。首页从 URL query 读 `tenant_id/kb_id` 预填。

- [ ] **Step 1: 建两个页面占位**

`frontend/src/pages/knowledge-file-tree.tsx`：

```tsx
import { AppHeader } from "@/components/app-header";

export function KnowledgeFileTreePage() {
  return (
    <div className="min-h-screen bg-muted/30">
      <AppHeader />
      <div className="container max-w-5xl py-8 space-y-6">
        <h1 className="text-2xl font-bold tracking-tight">知识库列表</h1>
      </div>
    </div>
  );
}
```

`frontend/src/pages/retrieve.tsx`：

```tsx
import { AppHeader } from "@/components/app-header";

export function RetrievePage() {
  return (
    <div className="min-h-screen bg-muted/30">
      <AppHeader />
      <div className="container max-w-3xl py-8 space-y-6">
        <h1 className="text-2xl font-bold tracking-tight">检索调试</h1>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 注册路由**

`frontend/src/router.tsx` 整体替换为：

```tsx
import { createBrowserRouter, Navigate } from "react-router-dom";
import { KnowledgeUploadPage } from "@/pages/knowledge-upload";
import { KnowledgeFileTreePage } from "@/pages/knowledge-file-tree";
import { RetrievePage } from "@/pages/retrieve";

export const router = createBrowserRouter([
  { path: "/", element: <KnowledgeUploadPage /> },
  { path: "/knowledge-bases", element: <KnowledgeFileTreePage /> },
  { path: "/retrieve", element: <RetrievePage /> },
  { path: "*", element: <Navigate to="/" replace /> },
]);
```

- [ ] **Step 3: 首页接入 AppHeader + 读 URL query**

`frontend/src/pages/knowledge-upload.tsx` 整体替换为：

```tsx
import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AppHeader } from "@/components/app-header";
import { CreateKnowledgeBase } from "@/components/create-knowledge-base";
import { UploadDocuments } from "@/components/upload-documents";

export function KnowledgeUploadPage() {
  const [searchParams] = useSearchParams();
  const [tenantId, setTenantId] = React.useState(
    () => searchParams.get("tenant_id") || "tenant_demo"
  );
  const [kbId, setKbId] = React.useState(() => searchParams.get("kb_id") || "");

  return (
    <div className="min-h-screen bg-muted/30">
      <AppHeader />
      <div className="container max-w-3xl py-8 space-y-6">
        <header className="space-y-1">
          <h1 className="text-2xl font-bold tracking-tight">RAG 知识库管理</h1>
          <p className="text-sm text-muted-foreground">
            创建知识库并上传文档，用于检索链路的调优测试。
          </p>
        </header>

        <div className="space-y-2 rounded-lg border bg-card p-4">
          <Label htmlFor="tenant-id">tenant_id</Label>
          <Input
            id="tenant-id"
            value={tenantId}
            onChange={(e) => setTenantId(e.target.value)}
            placeholder="tenant_demo"
          />
          <p className="text-xs text-muted-foreground">
            创建知识库和上传文档都会带上这个 tenant_id。
          </p>
        </div>

        <CreateKnowledgeBase tenantId={tenantId} onCreated={(kb) => setKbId(kb.kb_id)} />

        <UploadDocuments tenantId={tenantId} kbId={kbId} onKbIdChange={setKbId} />
      </div>
    </div>
  );
}
```

> `useState` 用惰性初始化读一次 query，避免每次 render 覆盖用户输入。上传主逻辑（`CreateKnowledgeBase`/`UploadDocuments`）不变。

- [ ] **Step 4: 类型检查 + 构建**

Run: `cd frontend && npm run typecheck && npm run build`
Expected: 均通过。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/router.tsx frontend/src/pages/
git commit -m "feat(fe): 注册两页路由，首页接入 AppHeader 并支持 URL 预填 tenant_id/kb_id

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: 前端 — 类型与 service（tree + retrieve）

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/services/knowledge-base.ts`
- Create: `frontend/src/services/rag.ts`

**Interfaces:**
- Produces:
  - types: `KnowledgeTreeDoc / KnowledgeTreeKb / KnowledgeTreeTenant`；`RetrieveMode`、`RetrieveRequest`、`RetrievedChunk`、`RetrievalMetadata`、`RerankMetadata`、`RetrieveMetadata`、`RetrieveData`
  - `fetchTree(keyword?: string): Promise<KnowledgeTreeTenant[]>`
  - `retrieve(payload: RetrieveRequest): Promise<RetrieveData>`

- [ ] **Step 1: 追加类型**

在 `frontend/src/types/api.ts` 末尾追加：

```ts
// ---- 知识库树形 ----
export interface KnowledgeTreeDoc {
  document_id: string;
  title: string;
  status: number;
  chunk_count: number;
  created_at: string;
}

export interface KnowledgeTreeKb {
  kb_id: string;
  name: string;
  description?: string | null;
  created_at: string;
  documents: KnowledgeTreeDoc[];
}

export interface KnowledgeTreeTenant {
  tenant_id: string;
  knowledge_bases: KnowledgeTreeKb[];
}

// ---- 检索 ----
export type RetrieveMode = "vector" | "bm25" | "hybrid";

export interface RetrieveRequest {
  tenant_id: string;
  kb_id: string;
  user_id: string;
  query: string;
  top_k?: number;
  retrieval_options?: {
    mode?: RetrieveMode;
    vector_top_k?: number;
    bm25_top_k?: number;
    rrf_k?: number;
  };
  rerank_options?: {
    enabled?: boolean;
    top_n?: number;
  };
}

export interface RetrievedChunk {
  document_id: string;
  chunk_id: string;
  title: string;
  content: string;
  score: number;
  vector_score?: number | null;
  bm25_score?: number | null;
  vector_rank?: number | null;
  bm25_rank?: number | null;
  retrieval_source?: string | null;
  rerank_score?: number | null;
}

export interface RetrievalMetadata {
  mode: string;
  fusion?: string | null;
  rrf_k?: number | null;
  vector_store?: string | null;
  keyword_search?: string | null;
  vector_top_k?: number | null;
  bm25_top_k?: number | null;
  vector_count?: number | null;
  bm25_count?: number | null;
  fused_count?: number | null;
  degraded: boolean;
  degraded_reason?: string | null;
}

export interface RerankMetadata {
  enabled: boolean;
  provider?: string | null;
  llm_provider?: string | null;
  model?: string | null;
  top_n?: number | null;
  candidate_count?: number | null;
  degraded: boolean;
  error?: string | null;
}

export interface RetrieveMetadata {
  top_k: number;
  vector_store: string;
  latency_ms: number;
  retrieval: RetrievalMetadata;
  rerank: RerankMetadata;
}

export interface RetrieveData {
  query: string;
  kb_id: string;
  retrieved_chunks: RetrievedChunk[];
  metadata: RetrieveMetadata;
}
```

- [ ] **Step 2: fetchTree service**

`frontend/src/services/knowledge-base.ts` 整体替换为：

```ts
import { http, unwrap } from "@/services/client";
import type {
  ApiResponse,
  CreateKnowledgeBaseRequest,
  KnowledgeBaseData,
  KnowledgeTreeTenant,
} from "@/types/api";

export function createKnowledgeBase(
  payload: CreateKnowledgeBaseRequest
): Promise<KnowledgeBaseData> {
  return unwrap(
    http.post<ApiResponse<KnowledgeBaseData>>("/v1/knowledge-bases/create", payload)
  );
}

export function fetchTree(keyword?: string): Promise<KnowledgeTreeTenant[]> {
  return unwrap(
    http.get<ApiResponse<KnowledgeTreeTenant[]>>("/v1/knowledge-bases/tree", {
      params: keyword ? { keyword } : undefined,
    })
  );
}
```

- [ ] **Step 3: retrieve service**

新建 `frontend/src/services/rag.ts`：

```ts
import { http, unwrap } from "@/services/client";
import type { ApiResponse, RetrieveData, RetrieveRequest } from "@/types/api";

export function retrieve(payload: RetrieveRequest): Promise<RetrieveData> {
  return unwrap(http.post<ApiResponse<RetrieveData>>("/v1/rag/retrieve", payload));
}
```

- [ ] **Step 4: 类型检查**

Run: `cd frontend && npm run typecheck`
Expected: 通过。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/services/
git commit -m "feat(fe): 新增 tree/retrieve 类型与 service

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: 前端 — 知识库列表页

**Files:**
- Modify: `frontend/src/pages/knowledge-file-tree.tsx`

**Interfaces:**
- Consumes: Task 7 的 `fetchTree`、tree 类型；`@tanstack/react-query`（已装）。

- [ ] **Step 1: 实现页面**

`frontend/src/pages/knowledge-file-tree.tsx` 整体替换为：

```tsx
import * as React from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { AppHeader } from "@/components/app-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { fetchTree } from "@/services/knowledge-base";
import type { KnowledgeTreeKb, KnowledgeTreeTenant } from "@/types/api";

export function KnowledgeFileTreePage() {
  const [keywordInput, setKeywordInput] = React.useState("");
  const [keyword, setKeyword] = React.useState("");
  const [expanded, setExpanded] = React.useState<Set<string>>(new Set());

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["kb-tree", keyword],
    queryFn: () => fetchTree(keyword || undefined),
  });

  const toggle = (key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const copyKbId = async (kbId: string) => {
    try {
      await navigator.clipboard.writeText(kbId);
      toast.success("已复制 kb_id");
    } catch {
      toast.error("复制失败");
    }
  };

  return (
    <div className="min-h-screen bg-muted/30">
      <AppHeader />
      <div className="container max-w-5xl py-8 space-y-6">
        <header className="space-y-1">
          <h1 className="text-2xl font-bold tracking-tight">知识库列表</h1>
          <p className="text-sm text-muted-foreground">
            按 租户 → 知识库 → 文档 三级展示，可跳转到上传或检索页。
          </p>
        </header>

        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setKeyword(keywordInput.trim());
          }}
        >
          <Input
            placeholder="按 tenant_id 模糊搜索，如 tech"
            value={keywordInput}
            onChange={(e) => setKeywordInput(e.target.value)}
          />
          <Button type="submit">搜索</Button>
        </form>

        {isLoading && <p className="text-sm text-muted-foreground">加载中…</p>}
        {isError && (
          <p className="text-sm text-destructive">
            加载失败：{(error as Error)?.message ?? "未知错误"}
          </p>
        )}
        {data && data.length === 0 && (
          <p className="text-sm text-muted-foreground">没有匹配的知识库。</p>
        )}

        <div className="space-y-2">
          {data?.map((tenant) => (
            <TenantRow
              key={tenant.tenant_id}
              tenant={tenant}
              expanded={expanded}
              onToggle={toggle}
              onCopy={copyKbId}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function TenantRow({
  tenant,
  expanded,
  onToggle,
  onCopy,
}: {
  tenant: KnowledgeTreeTenant;
  expanded: Set<string>;
  onToggle: (key: string) => void;
  onCopy: (kbId: string) => void;
}) {
  const key = `t:${tenant.tenant_id}`;
  const open = expanded.has(key);
  return (
    <div className="rounded-lg border bg-card">
      <button
        type="button"
        className="flex w-full items-center gap-2 px-4 py-3 text-left font-medium"
        onClick={() => onToggle(key)}
      >
        <span className="w-3 text-muted-foreground">{open ? "▾" : "▶"}</span>
        <span>{tenant.tenant_id}</span>
        <span className="text-xs text-muted-foreground">
          （{tenant.knowledge_bases.length} 个知识库）
        </span>
      </button>
      {open && (
        <div className="space-y-2 px-4 pb-3">
          {tenant.knowledge_bases.map((kb) => (
            <KbRow
              key={kb.kb_id}
              kb={kb}
              tenantId={tenant.tenant_id}
              expanded={expanded}
              onToggle={onToggle}
              onCopy={onCopy}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function KbRow({
  kb,
  tenantId,
  expanded,
  onToggle,
  onCopy,
}: {
  kb: KnowledgeTreeKb;
  tenantId: string;
  expanded: Set<string>;
  onToggle: (key: string) => void;
  onCopy: (kbId: string) => void;
}) {
  const key = `k:${kb.kb_id}`;
  const open = expanded.has(key);
  const query = `tenant_id=${encodeURIComponent(tenantId)}&kb_id=${encodeURIComponent(kb.kb_id)}`;
  return (
    <div className="rounded-md border bg-background">
      <div className="flex items-center gap-2 px-3 py-2">
        <button
          type="button"
          className="flex flex-1 items-center gap-2 text-left"
          onClick={() => onToggle(key)}
        >
          <span className="w-3 text-muted-foreground">{open ? "▾" : "▶"}</span>
          <span className="font-medium">{kb.name}</span>
          <span className="font-mono text-xs text-muted-foreground">
            kb_id: {kb.kb_id.slice(0, 8)}…
          </span>
          <span className="text-xs text-muted-foreground">
            （{kb.documents.length} 个文档）
          </span>
        </button>
        <div className="flex shrink-0 gap-2">
          <Button size="sm" variant="outline" onClick={() => onCopy(kb.kb_id)}>
            复制 kb_id
          </Button>
          <Button size="sm" variant="outline" asChild>
            <Link to={`/?${query}`}>去上传</Link>
          </Button>
          <Button size="sm" variant="outline" asChild>
            <Link to={`/retrieve?${query}`}>去检索</Link>
          </Button>
        </div>
      </div>
      {open && (
        <div className="px-3 pb-2">
          {kb.documents.length === 0 ? (
            <p className="py-2 text-xs text-muted-foreground">暂无成功索引的文档。</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground">
                  <th className="py-1">文件</th>
                  <th className="py-1">document_id</th>
                  <th className="py-1">chunk 数</th>
                </tr>
              </thead>
              <tbody>
                {kb.documents.map((d) => (
                  <tr key={d.document_id} className="border-t">
                    <td className="py-1">{d.title}</td>
                    <td className="py-1 font-mono text-xs">{d.document_id}</td>
                    <td className="py-1">{d.chunk_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
```

> `tenant_id` 由 `TenantRow` 下传给 `KbRow` 用于拼跳转 URL（`KnowledgeTreeKb` 本身不含该字段）。

- [ ] **Step 2: 类型检查 + 构建**

Run: `cd frontend && npm run typecheck && npm run build`
Expected: 均通过。

- [ ] **Step 3: 手动验证（需后端运行）**

启动后端与前端 `npm run dev`，浏览器打开 `/knowledge-bases`：
- 输入 `tech` 搜索能按 tenant_id 过滤。
- 展开租户 → 知识库 → 文档三级正常，文档只显示成功记录、显示 chunk 数。
- 「复制 kb_id」toast 成功；「去上传」跳 `/?tenant_id=...&kb_id=...` 且表单预填；「去检索」跳 `/retrieve?...`。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/knowledge-file-tree.tsx
git commit -m "feat(fe): 知识库树形列表页

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: 前端 — 检索调试页

**Files:**
- Modify: `frontend/src/pages/retrieve.tsx`

**Interfaces:**
- Consumes: Task 7 的 `retrieve`、retrieve 类型；`useSearchParams`；`useMutation`。

- [ ] **Step 1: 实现页面**

`frontend/src/pages/retrieve.tsx` 整体替换为：

```tsx
import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { AppHeader } from "@/components/app-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { retrieve } from "@/services/rag";
import type { RetrieveMode, RetrieveRequest, RetrievedChunk, RetrieveData } from "@/types/api";

const MODES: RetrieveMode[] = ["vector", "bm25", "hybrid"];

// 100px 右对齐的标签 + 同行控件
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-[100px] shrink-0 text-right text-sm text-muted-foreground">{label}</span>
      <div className="flex flex-1 items-center gap-2">{children}</div>
    </div>
  );
}

export function RetrievePage() {
  const [searchParams] = useSearchParams();
  const [tenantId, setTenantId] = React.useState(() => searchParams.get("tenant_id") || "");
  const [kbId, setKbId] = React.useState(() => searchParams.get("kb_id") || "");
  const [query, setQuery] = React.useState("");
  const [configOpen, setConfigOpen] = React.useState(true);

  const [topK, setTopK] = React.useState(5);
  const [mode, setMode] = React.useState<RetrieveMode>("hybrid");
  const [vectorTopK, setVectorTopK] = React.useState(20);
  const [bm25TopK, setBm25TopK] = React.useState(20);
  const [rrfK, setRrfK] = React.useState(60);
  const [rerankEnabled, setRerankEnabled] = React.useState(true);
  const [rerankTopN, setRerankTopN] = React.useState(5);

  const mutation = useMutation<RetrieveData, Error, RetrieveRequest>({
    mutationFn: retrieve,
    onError: (e) => toast.error(e.message),
  });

  const onSubmit = () => {
    if (!tenantId.trim()) return toast.error("请填写 tenant_id");
    if (!kbId.trim()) return toast.error("请填写 kb_id");
    if (!query.trim()) return toast.error("请填写 query");

    const payload: RetrieveRequest = {
      tenant_id: tenantId.trim(),
      kb_id: kbId.trim(),
      user_id: "debug_user",
      query: query.trim(),
      top_k: topK,
      retrieval_options: {
        mode,
        ...(mode === "hybrid"
          ? { vector_top_k: vectorTopK, bm25_top_k: bm25TopK, rrf_k: rrfK }
          : {}),
      },
      ...(rerankEnabled ? { rerank_options: { enabled: true, top_n: rerankTopN } } : {}),
    };
    mutation.mutate(payload);
  };

  const result = mutation.data;

  return (
    <div className="min-h-screen bg-muted/30">
      <AppHeader />
      <div className="container max-w-3xl space-y-6 py-8">
        <header className="space-y-1">
          <h1 className="text-2xl font-bold tracking-tight">检索调试</h1>
          <p className="text-sm text-muted-foreground">输入 query 直接查看召回结果与评分明细。</p>
        </header>

        {/* Card 1: 检索配置 */}
        <Card>
          <CardHeader className="cursor-pointer" onClick={() => setConfigOpen((v) => !v)}>
            <CardTitle className="flex items-center gap-2 text-base">
              <span>{configOpen ? "▾" : "▶"}</span> 检索配置
            </CardTitle>
          </CardHeader>
          {configOpen && (
            <CardContent className="space-y-4">
              <div className="space-y-3 rounded-md border bg-muted/40 p-3">
                <Field label="tenant_id">
                  <Input value={tenantId} onChange={(e) => setTenantId(e.target.value)} />
                </Field>
                <Field label="kb_id">
                  <Input value={kbId} onChange={(e) => setKbId(e.target.value)} />
                </Field>
              </div>

              <Field label="top_k">
                <Input
                  type="number"
                  className="w-28"
                  value={topK}
                  onChange={(e) => setTopK(Number(e.target.value))}
                />
              </Field>

              <Field label="检索模式">
                {MODES.map((m) => (
                  <Button
                    key={m}
                    type="button"
                    size="sm"
                    variant={mode === m ? "default" : "outline"}
                    onClick={() => setMode(m)}
                  >
                    {m}
                  </Button>
                ))}
              </Field>

              {mode === "hybrid" && (
                <Field label="hybrid 参数">
                  <label className="text-xs text-muted-foreground">vector_top_k</label>
                  <Input
                    type="number"
                    className="w-20"
                    value={vectorTopK}
                    onChange={(e) => setVectorTopK(Number(e.target.value))}
                  />
                  <label className="text-xs text-muted-foreground">bm25_top_k</label>
                  <Input
                    type="number"
                    className="w-20"
                    value={bm25TopK}
                    onChange={(e) => setBm25TopK(Number(e.target.value))}
                  />
                  <label className="text-xs text-muted-foreground">rrf_k</label>
                  <Input
                    type="number"
                    className="w-20"
                    value={rrfK}
                    onChange={(e) => setRrfK(Number(e.target.value))}
                  />
                </Field>
              )}

              <Field label="rerank">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={rerankEnabled}
                    onChange={(e) => setRerankEnabled(e.target.checked)}
                  />
                  启用
                </label>
                {rerankEnabled && (
                  <>
                    <label className="text-xs text-muted-foreground">top_n</label>
                    <Input
                      type="number"
                      className="w-20"
                      value={rerankTopN}
                      onChange={(e) => setRerankTopN(Number(e.target.value))}
                    />
                  </>
                )}
              </Field>
            </CardContent>
          )}
        </Card>

        {/* Card 2: 检索与召回 */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">检索与召回</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Textarea
              rows={3}
              placeholder="输入 query"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <Button onClick={onSubmit} disabled={mutation.isPending}>
              {mutation.isPending ? "检索中…" : "检索"}
            </Button>

            {result && (
              <div className="space-y-3">
                <div className="text-sm text-muted-foreground">召回结果</div>
                {result.retrieved_chunks.map((c, i) => (
                  <ChunkCard key={c.chunk_id} rank={i + 1} chunk={c} />
                ))}
                {result.retrieved_chunks.length === 0 && (
                  <p className="text-sm text-muted-foreground">无召回结果。</p>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Card 3: 运行摘要 */}
        {result && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">运行摘要</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-sm">
              <div>
                mode={result.metadata.retrieval.mode} | top_k={result.metadata.top_k} | 服务端耗时{" "}
                {result.metadata.latency_ms}ms
              </div>
              <div className="text-muted-foreground">
                vector:{result.metadata.retrieval.vector_count ?? "—"} bm25:
                {result.metadata.retrieval.bm25_count ?? "—"} fused:
                {result.metadata.retrieval.fused_count ?? "—"}
              </div>
              <div className="text-muted-foreground">
                rerank: {result.metadata.rerank.enabled ? "启用" : "关闭"}
                {result.metadata.rerank.model ? ` / ${result.metadata.rerank.model}` : ""}
                {result.metadata.retrieval.degraded ? " | ⚠ hybrid degraded" : ""}
                {result.metadata.rerank.degraded ? " | ⚠ rerank degraded" : ""}
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

function ChunkCard({ rank, chunk }: { rank: number; chunk: RetrievedChunk }) {
  const [open, setOpen] = React.useState(false);
  const fmt = (v?: number | null) => (v === null || v === undefined ? "—" : v.toFixed(2));
  return (
    <div className="rounded-md border bg-background p-3 text-sm">
      <div className="font-mono text-xs">
        #{rank} score={fmt(chunk.score)} vector={fmt(chunk.vector_score)} bm25=
        {fmt(chunk.bm25_score)} rerank={fmt(chunk.rerank_score)}
      </div>
      <div className="mt-1 text-muted-foreground">
        {chunk.title} / {chunk.document_id} / {chunk.chunk_id}
      </div>
      <button
        type="button"
        className="mt-1 text-xs text-primary"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? "收起内容" : "展开内容"}
      </button>
      {open && <p className="mt-1 whitespace-pre-wrap">{chunk.content}</p>}
    </div>
  );
}
```

- [ ] **Step 2: 类型检查 + 构建**

Run: `cd frontend && npm run typecheck && npm run build`
Expected: 均通过。

- [ ] **Step 3: 手动验证（需后端运行）**

- 从列表页「去检索」进入，`tenant_id/kb_id` 已预填。
- 切到 `hybrid` 时才出现 vector_top_k/bm25_top_k/rrf_k 三个子参数且同一行；切到 vector/bm25 时隐藏。
- 关闭 rerank 后请求体不含 `rerank_options`（可在浏览器 Network 面板确认）。
- 输入 query 点检索，召回列表展示分数、title/document_id/chunk_id、内容可折叠。
- 运行摘要显示服务端 `latency_ms`、mode、count、degraded、rerank 模型名。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/retrieve.tsx
git commit -m "feat(fe): 检索调试页

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## 验收自查（对照 spec 第六节）

- 多租户多库多文档树形展示 → Task 4 + 8
- 文档层只显示 SUCCESS → Task 3（`list_success_by_kb_ids`）
- 搜索按 tenant_id 模糊过滤 → Task 3（`list_all` ILIKE）+ 8
- 去上传预填 tenant_id/kb_id → Task 6（首页读 query）+ 8（拼 URL）
- 去检索预填 → Task 6/9 + 8
- 检索召回列表展示 → Task 9
- hybrid 子参数仅 hybrid 显示且同行 → Task 9
- rerank 开关联动、禁用不传 rerank_options → Task 9
- 运行摘要展示服务端 latency_ms → Task 1 + 9
- AppHeader 三页导航按路由切换 → Task 5 + 6/8/9
- 首页上传逻辑不变 → Task 6（仅加 header 与 query 预填）
