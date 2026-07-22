# 提问语义优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在检索前插入两层可选处理（LLM 改问、词表扩展），用扩展后的 search_query 做检索，两层默认关闭且失败自动降级。

**Architecture:** 新增 `app/providers/query/` 目录实现 `QueryProcessor` 抽象（noop / llm_rewrite / synonym）与 `QueryPipeline` 串联；`knowledge_bases.settings` JSONB 存 kb 级词表与 rewrite_hint；`RAGService.retrieve` 在 kb 校验后、召回前调用 pipeline，用 `search_query` 送检索；请求 `query_options`、响应 `metadata.query_processing` 透出链路；调试台加改写开关与摘要展示。

**Tech Stack:** FastAPI + SQLAlchemy(async) + Alembic + Pydantic v2 + pytest；前端 React18 + Vite + react-query + shadcn/ui。

## Global Constraints

- 两层默认关闭：全局 `QUERY_REWRITE_ENABLED=false`；请求级 `query_options` 优先于全局。
- 词表扩展无全局开关：只要 kb.settings 有 synonyms 就尝试，不受 `query_options.enabled` 控制。
- LLM 改写失败（超时/报错/空）必须降级：`effective_query = raw_query`，`degraded=true`，检索照常，绝不 500。
- 改写耗时 `rewrite_latency_ms` 单独计，不混入检索 `latency_ms`。
- `RetrieveData.query` 仍返回用户原始 query；rerank 仍用 `request.query`，不用 search_query。
- 全无处理时 `metadata.query_processing` 返回 `null`，与改前兼容。
- LLM 复用现有 `LLMProvider`/`LLM_*` 配置，不新增模型配置。
- 词表仅对当前 kb 生效，不跨库、不跨租户。
- 中文 term 精确子串匹配；英文 term 忽略大小写。多组命中 expand 去重后追加。
- rewrite_hint 拼接规则：传给 Prompt 的领域说明 = `description + "\n" + rewrite_hint`（有 rewrite_hint 时），需在代码注释写明。
- 不做词表在线编辑 UI。
- 约定：全程自动推进不逐步确认；**不 commit**，改动留在工作区。

---

### Task 1: DB — knowledge_bases.settings 字段 + 迁移 + repo/service

**Files:**
- Modify: `app/models/knowledge_base.py`
- Modify: `app/repositories/knowledge_base_repository.py`
- Modify: `app/services/knowledge_base_service.py:37-42`
- Create: `migrations/versions/0003_kb_settings.py`
- Test: `tests/test_kb_settings_repo.py`

**Interfaces:**
- Produces: `KnowledgeBase.settings: dict`（JSONB, NOT NULL default `{}`）；`KnowledgeBaseRepository.update_settings(kb_id, settings) -> KnowledgeBase | None`；create 时 settings 默认 `{}`。

- [ ] **Step 1: 给 model 增加 settings 字段**

`app/models/knowledge_base.py` 顶部 import 增加 `JSONB`，字段追加在 `description` 之后：

```python
from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB
```
```python
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # kb 级配置：词表 synonyms、改写领域提示 rewrite_hint 等（由运维脚本维护）
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
```

- [ ] **Step 2: repo 增加 update_settings**

`app/repositories/knowledge_base_repository.py` 类内追加：

```python
    async def update_settings(self, kb_id: str, settings: dict) -> KnowledgeBase | None:
        kb = await self._session.get(KnowledgeBase, kb_id)
        if kb is None:
            return None
        kb.settings = settings
        await self._session.flush()
        return kb
```

- [ ] **Step 3: create 时带默认 settings**

`app/services/knowledge_base_service.py` 的 `KnowledgeBase(...)` 构造追加 `settings={}`：

```python
        kb = KnowledgeBase(
            id=new_kb_id(),
            tenant_id=tenant_id,
            name=req.name,
            description=req.description,
            settings={},
        )
```

- [ ] **Step 4: 写 Alembic 迁移 0003**

`migrations/versions/0003_kb_settings.py`（对齐 0002 命名风格，down_revision 指向 0002）:

```python
"""add knowledge_bases.settings

Revision ID: 0003_kb_settings
Revises: 0002_auth
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003_kb_settings"
down_revision = "0002_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_bases",
        sa.Column("settings", JSONB(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("knowledge_bases", "settings")
```

> 若 0002 的实际 revision id 不是 `0002_auth`，用 `alembic heads` 确认后替换 down_revision。

- [ ] **Step 5: 写测试（settings 默认值与 update）**

`tests/test_kb_settings_repo.py`（用现有 test 的 in-memory/session fixture 模式；若仓库测试用 sqlite JSON 兼容，沿用现有 conftest）:

```python
import pytest
from app.models.knowledge_base import KnowledgeBase


def test_kb_settings_defaults_to_empty_dict():
    kb = KnowledgeBase(id="kb-x", tenant_id="t1", name="n", description=None, settings={})
    assert kb.settings == {}


@pytest.mark.asyncio
async def test_update_settings_overwrites(kb_repo_and_session):
    repo, session = kb_repo_and_session
    kb = KnowledgeBase(id="kb-1", tenant_id="t1", name="n", description=None, settings={})
    await repo.create(kb)
    await session.flush()
    updated = await repo.update_settings("kb-1", {"synonyms": [{"terms": ["背调"], "expand": ["背景调查"]}]})
    assert updated is not None
    assert updated.settings["synonyms"][0]["terms"] == ["背调"]
    assert await repo.update_settings("missing", {}) is None
```

> 若无 `kb_repo_and_session` fixture，改为纯 model 单测（Step 的第一个用例）+ 在 Task 8 的集成层覆盖 update；不要为此新建 DB fixture 基建。

- [ ] **Step 6: 跑测试**

Run: `.venv/bin/python -m pytest tests/test_kb_settings_repo.py -v`
Expected: PASS（无 async fixture 时至少 model 默认值用例 PASS）

---

### Task 2: QueryProcessResult 数据结构 + base 抽象 + noop

**Files:**
- Create: `app/providers/query/__init__.py`
- Create: `app/providers/query/base.py`
- Create: `app/providers/query/noop.py`
- Test: `tests/test_query_pipeline.py`

**Interfaces:**
- Produces: `QueryProcessResult`（dataclass，字段见下）；`QueryProcessor` 抽象基类 `async def process(self, result: QueryProcessResult, *, kb_name, kb_description, kb_settings) -> QueryProcessResult`；`NoopProcessor`。

- [ ] **Step 1: 写失败测试**

`tests/test_query_pipeline.py`:

```python
import pytest
from app.providers.query.base import QueryProcessResult
from app.providers.query.noop import NoopProcessor


def test_result_from_raw_initializes_all_stages():
    r = QueryProcessResult.from_raw("背调要问啥")
    assert r.raw_query == "背调要问啥"
    assert r.effective_query == "背调要问啥"
    assert r.search_query == "背调要问啥"
    assert r.strategy == "noop"
    assert r.degraded is False
    assert r.synonym_applied is False
    assert r.synonym_expansions == []


@pytest.mark.asyncio
async def test_noop_processor_is_passthrough():
    r = QueryProcessResult.from_raw("hi")
    out = await NoopProcessor().process(r, kb_name="k", kb_description=None, kb_settings={})
    assert out.effective_query == "hi"
    assert out.search_query == "hi"
    assert out.strategy == "noop"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_query_pipeline.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 写 base.py**

`app/providers/query/base.py`:

```python
"""提问语义优化的数据结构与处理器抽象。

QueryProcessResult 覆盖同一 query 的三个阶段：
    raw_query      用户原话，全程不变
    effective_query LLM 改写后的句子，未改写时等于 raw_query
    search_query   词表扩展后实际送入检索的最终句子，无扩展时等于 effective_query
业务代码始终用 search_query 检索即可。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class QueryProcessResult:
    raw_query: str
    effective_query: str
    search_query: str
    strategy: str = "noop"          # noop 或 rewrite
    rewrite_latency_ms: int = 0      # 改写耗时，单独计，不混入检索 latency_ms
    degraded: bool = False           # LLM 改写是否失败并回退
    degraded_reason: str | None = None
    synonym_applied: bool = False
    synonym_expansions: list[str] = field(default_factory=list)

    @classmethod
    def from_raw(cls, raw_query: str) -> "QueryProcessResult":
        return cls(raw_query=raw_query, effective_query=raw_query, search_query=raw_query)


class QueryProcessor(ABC):
    @abstractmethod
    async def process(
        self,
        result: QueryProcessResult,
        *,
        kb_name: str,
        kb_description: str | None,
        kb_settings: dict,
    ) -> QueryProcessResult:
        """就地推进 result 的某一阶段并返回。处理器之间通过 result 传递状态。"""
        raise NotImplementedError
```

- [ ] **Step 4: 写 noop.py 与 __init__.py**

`app/providers/query/__init__.py`: 空文件。

`app/providers/query/noop.py`:

```python
"""直通处理器，不做任何改写或扩展。"""
from __future__ import annotations

from app.providers.query.base import QueryProcessor, QueryProcessResult


class NoopProcessor(QueryProcessor):
    async def process(self, result, *, kb_name, kb_description, kb_settings):
        return result
```

- [ ] **Step 5: 跑测试**

Run: `.venv/bin/python -m pytest tests/test_query_pipeline.py -v`
Expected: PASS

---

### Task 3: 词表扩展 synonym_expander（纯函数）

**Files:**
- Create: `app/providers/query/synonym_expander.py`
- Test: `tests/test_query_pipeline.py`（追加）

**Interfaces:**
- Consumes: `QueryProcessResult`, `QueryProcessor`
- Produces: `SynonymExpander()`；命中时把去重后的 expand 词以空格追加到 `effective_query` 得到 `search_query`，并置 `synonym_applied=True`、`synonym_expansions=[...]`。

- [ ] **Step 1: 写失败测试（追加到 tests/test_query_pipeline.py）**

```python
from app.providers.query.synonym_expander import SynonymExpander

_SYN = {
    "synonyms": [
        {"terms": ["背调"], "expand": ["背景调查", "标准问题清单"]},
        {"terms": ["薪酬", "薪资"], "expand": ["职级", "薪酬定级"]},
    ]
}


@pytest.mark.asyncio
async def test_synonym_hit_appends_dedup_expansions():
    r = QueryProcessResult.from_raw("背调要问啥")
    out = await SynonymExpander().process(r, kb_name="hr", kb_description=None, kb_settings=_SYN)
    assert out.synonym_applied is True
    assert out.synonym_expansions == ["背景调查", "标准问题清单"]
    assert out.search_query == "背调要问啥 背景调查 标准问题清单"


@pytest.mark.asyncio
async def test_synonym_multi_group_dedup_and_english_case_insensitive():
    settings = {"synonyms": [
        {"terms": ["KPI"], "expand": ["考核", "指标"]},
        {"terms": ["okr"], "expand": ["指标", "目标"]},
    ]}
    r = QueryProcessResult.from_raw("聊聊 kpi 和 OKR")
    out = await SynonymExpander().process(r, kb_name="hr", kb_description=None, kb_settings=settings)
    assert out.synonym_applied is True
    # 去重后保持首次出现顺序
    assert out.synonym_expansions == ["考核", "指标", "目标"]


@pytest.mark.asyncio
async def test_synonym_miss_keeps_effective_query():
    r = QueryProcessResult.from_raw("今天天气")
    out = await SynonymExpander().process(r, kb_name="hr", kb_description=None, kb_settings=_SYN)
    assert out.synonym_applied is False
    assert out.search_query == "今天天气"


@pytest.mark.asyncio
async def test_synonym_no_settings_is_noop():
    r = QueryProcessResult.from_raw("背调要问啥")
    out = await SynonymExpander().process(r, kb_name="hr", kb_description=None, kb_settings={})
    assert out.synonym_applied is False
    assert out.search_query == "背调要问啥"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_query_pipeline.py -k synonym -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 写 synonym_expander.py**

`app/providers/query/synonym_expander.py`:

```python
"""词表扩展：纯函数逻辑，不调 LLM。

词表存在 kb.settings.synonyms，由运维脚本维护，不进平台代码。
匹配规则：中文 term 精确子串匹配；英文 term 忽略大小写。命中组的 expand
追加到 effective_query 末尾（空格分隔），多组命中去重（保持首次出现顺序）。
未命中时 search_query 等于 effective_query。词表仅对当前 kb 生效。
"""
from __future__ import annotations

from app.providers.query.base import QueryProcessor, QueryProcessResult


def _term_hit(term: str, query: str) -> bool:
    # 英文 term 忽略大小写；中文精确子串。统一用 lower 比较即可覆盖两者
    # （中文 lower 无副作用）。
    return term.lower() in query.lower()


class SynonymExpander(QueryProcessor):
    async def process(self, result, *, kb_name, kb_description, kb_settings):
        groups = (kb_settings or {}).get("synonyms") or []
        base = result.effective_query
        expansions: list[str] = []
        for group in groups:
            terms = group.get("terms") or []
            if any(_term_hit(t, base) for t in terms):
                for w in group.get("expand") or []:
                    if w not in expansions:
                        expansions.append(w)
        if expansions:
            result.synonym_applied = True
            result.synonym_expansions = expansions
            result.search_query = base + " " + " ".join(expansions)
        else:
            result.search_query = base
        return result
```

- [ ] **Step 4: 跑测试**

Run: `.venv/bin/python -m pytest tests/test_query_pipeline.py -k synonym -v`
Expected: PASS

---

### Task 4: LLM 改写 llm_rewrite（含降级）

**Files:**
- Create: `app/providers/query/llm_rewrite.py`
- Test: `tests/test_query_pipeline.py`（追加）

**Interfaces:**
- Consumes: `LLMProvider.chat_json(...)`, `QueryProcessResult`
- Produces: `LLMRewriteProcessor(llm_provider, *, timeout_ms=None, temperature=0.0)`；成功时 `effective_query=改写句`、`strategy="rewrite"`、`rewrite_latency_ms=耗时`；失败降级 `effective_query=raw_query`、`degraded=True`、`degraded_reason=...`，绝不抛出。

- [ ] **Step 1: 写失败测试（追加）**

```python
from app.providers.query.llm_rewrite import LLMRewriteProcessor
from app.core.exceptions import LLMProviderError


class _FakeLLM:
    def __init__(self, ret=None, exc=None):
        self._ret, self._exc = ret, exc
        self.calls = []

    async def chat_json(self, *, system_prompt, user_payload, temperature=0.0, timeout_seconds=None):
        self.calls.append(user_payload)
        if self._exc:
            raise self._exc
        return self._ret


@pytest.mark.asyncio
async def test_rewrite_success_sets_effective_query():
    llm = _FakeLLM(ret={"rewritten_query": "背景调查标准问题有哪些"})
    r = QueryProcessResult.from_raw("背调要问啥")
    out = await LLMRewriteProcessor(llm).process(r, kb_name="HR库", kb_description="招聘制度", kb_settings={})
    assert out.effective_query == "背景调查标准问题有哪些"
    assert out.strategy == "rewrite"
    assert out.degraded is False
    # description + rewrite_hint 拼接进 payload
    assert llm.calls[0]["kb_description"] == "招聘制度"


@pytest.mark.asyncio
async def test_rewrite_uses_rewrite_hint():
    llm = _FakeLLM(ret={"rewritten_query": "x"})
    r = QueryProcessResult.from_raw("q")
    await LLMRewriteProcessor(llm).process(
        r, kb_name="k", kb_description="领域说明", kb_settings={"rewrite_hint": "SB=背调"}
    )
    assert llm.calls[0]["kb_description"] == "领域说明\nSB=背调"


@pytest.mark.asyncio
async def test_rewrite_degrades_on_error():
    llm = _FakeLLM(exc=LLMProviderError("boom"))
    r = QueryProcessResult.from_raw("背调要问啥")
    out = await LLMRewriteProcessor(llm).process(r, kb_name="k", kb_description=None, kb_settings={})
    assert out.effective_query == "背调要问啥"
    assert out.degraded is True
    assert out.degraded_reason


@pytest.mark.asyncio
async def test_rewrite_degrades_on_empty():
    llm = _FakeLLM(ret={"rewritten_query": "  "})
    r = QueryProcessResult.from_raw("背调要问啥")
    out = await LLMRewriteProcessor(llm).process(r, kb_name="k", kb_description=None, kb_settings={})
    assert out.effective_query == "背调要问啥"
    assert out.degraded is True
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_query_pipeline.py -k rewrite -v`
Expected: FAIL

- [ ] **Step 3: 写 llm_rewrite.py**

`app/providers/query/llm_rewrite.py`:

```python
"""LLM 改问法：把口语 query 改成更贴近文档表述的检索句。

复用现有 LLMProvider，不新增模型配置。只传用户原话 + kb 名称 + 领域说明，
不读文档正文以避免 token 膨胀。若 kb.settings 配了 rewrite_hint，则领域说明
= description + "\\n" + rewrite_hint（rewrite_hint 用于业务方补充缩写含义等）。

降级：LLM 超时/报错/返回空时，effective_query 回退为 raw_query，标记 degraded，
检索照常继续，绝不抛出。改写耗时单独记录，不算进检索 latency_ms。
"""
from __future__ import annotations

import time

from app.core.config import settings
from app.core.exceptions import LLMProviderError
from app.core.logging import get_logger
from app.providers.llm.base import LLMProvider
from app.providers.query.base import QueryProcessor, QueryProcessResult

logger = get_logger(__name__)

_SYSTEM_PROMPT = """你是检索 query 改写器，不是问答助手。
输入：用户原话 + 知识库名称 + 知识库领域说明。
输出：一条中文短句，更贴近文档常用表述，不超过 30 字。
不编造事实，不扩展用户没问的内容，不生成答案。
只输出改写后的句子，放在 JSON 字段 rewritten_query 中，不输出解释。
返回格式：{"rewritten_query": "..."}"""


class LLMRewriteProcessor(QueryProcessor):
    def __init__(self, llm_provider: LLMProvider, *, timeout_ms: int | None = None, temperature: float = 0.0):
        self._llm = llm_provider
        self._timeout_ms = timeout_ms if timeout_ms is not None else settings.query_rewrite_timeout_ms
        self._temperature = temperature

    async def process(self, result, *, kb_name, kb_description, kb_settings):
        # 领域说明 = description + "\n" + rewrite_hint（有 hint 时）
        desc = kb_description or ""
        hint = (kb_settings or {}).get("rewrite_hint")
        if hint:
            desc = f"{desc}\n{hint}" if desc else hint

        payload = {
            "raw_query": result.raw_query,
            "kb_name": kb_name,
            "kb_description": desc,
        }
        started = time.perf_counter()
        try:
            raw = await self._llm.chat_json(
                system_prompt=_SYSTEM_PROMPT,
                user_payload=payload,
                temperature=self._temperature,
                timeout_seconds=max(1, round(self._timeout_ms / 1000)),
            )
            rewritten = (raw or {}).get("rewritten_query") or ""
            rewritten = rewritten.strip()
            if not rewritten:
                raise LLMProviderError("empty rewritten_query")
            result.effective_query = rewritten
            result.strategy = "rewrite"
        except (LLMProviderError, Exception) as exc:  # 任何异常都降级，绝不 500
            result.degraded = True
            result.degraded_reason = str(exc)[:200]
            result.effective_query = result.raw_query
            result.strategy = "rewrite"
            logger.warning("QUERY_REWRITE_DEGRADED | reason=%s", result.degraded_reason)
        finally:
            result.rewrite_latency_ms = int((time.perf_counter() - started) * 1000)
        return result
```

- [ ] **Step 4: 跑测试**

Run: `.venv/bin/python -m pytest tests/test_query_pipeline.py -k rewrite -v`
Expected: PASS

---

### Task 5: QueryPipeline 串联

**Files:**
- Create: `app/providers/query/pipeline.py`
- Test: `tests/test_query_pipeline.py`（追加）

**Interfaces:**
- Consumes: `NoopProcessor`, `LLMRewriteProcessor`, `SynonymExpander`, `QueryProcessResult`
- Produces: `QueryPipeline(llm_provider)` 带 `async def run(self, raw_query, *, rewrite_enabled, kb_name, kb_description, kb_settings) -> QueryProcessResult`。改写按 `rewrite_enabled` 决定；词表始终尝试（有 settings 就跑）。

- [ ] **Step 1: 写失败测试（追加）**

```python
from app.providers.query.pipeline import QueryPipeline


@pytest.mark.asyncio
async def test_pipeline_rewrite_off_synonym_still_runs():
    llm = _FakeLLM(ret={"rewritten_query": "SHOULD_NOT_BE_USED"})
    p = QueryPipeline(llm)
    out = await p.run("背调要问啥", rewrite_enabled=False, kb_name="hr", kb_description=None, kb_settings=_SYN)
    assert out.effective_query == "背调要问啥"          # 未改写
    assert out.strategy == "noop"
    assert out.synonym_applied is True                   # 词表仍生效
    assert "背景调查" in out.search_query
    assert llm.calls == []                               # 未调 LLM


@pytest.mark.asyncio
async def test_pipeline_rewrite_on_then_synonym():
    llm = _FakeLLM(ret={"rewritten_query": "背调标准问题"})
    p = QueryPipeline(llm)
    out = await p.run("背调要问啥", rewrite_enabled=True, kb_name="hr", kb_description="招聘", kb_settings=_SYN)
    assert out.effective_query == "背调标准问题"
    # 词表基于 effective_query 匹配（含"背调"）
    assert out.synonym_applied is True
    assert out.search_query.startswith("背调标准问题 ")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_query_pipeline.py -k pipeline -v`
Expected: FAIL

- [ ] **Step 3: 写 pipeline.py**

`app/providers/query/pipeline.py`:

```python
"""串联提问语义优化两层：LLM 改写（可选）→ 词表扩展（有 settings 即尝试）。

按 rewrite_enabled 决定是否改写（请求级优先于全局，由调用方在传入前解析好）。
词表扩展始终执行，不受 rewrite_enabled 控制。
"""
from __future__ import annotations

from app.providers.llm.base import LLMProvider
from app.providers.query.base import QueryProcessResult
from app.providers.query.llm_rewrite import LLMRewriteProcessor
from app.providers.query.synonym_expander import SynonymExpander


class QueryPipeline:
    def __init__(self, llm_provider: LLMProvider):
        self._llm = llm_provider
        self._synonym = SynonymExpander()

    async def run(
        self,
        raw_query: str,
        *,
        rewrite_enabled: bool,
        kb_name: str,
        kb_description: str | None,
        kb_settings: dict,
    ) -> QueryProcessResult:
        result = QueryProcessResult.from_raw(raw_query)
        ctx = dict(kb_name=kb_name, kb_description=kb_description, kb_settings=kb_settings)
        if rewrite_enabled:
            result = await LLMRewriteProcessor(self._llm).process(result, **ctx)
        # 词表扩展始终尝试（无 synonyms 时是直通）
        result = await self._synonym.process(result, **ctx)
        return result
```

- [ ] **Step 4: 跑测试**

Run: `.venv/bin/python -m pytest tests/test_query_pipeline.py -v`
Expected: PASS（全部 query pipeline 用例）

---

### Task 6: 配置项 + Schema（query_options / query_processing）

**Files:**
- Modify: `app/core/config.py`（Settings 追加两项）
- Modify: `.env.example`
- Modify: `app/schemas/rag.py`
- Test: `tests/test_query_schema.py`

**Interfaces:**
- Produces: `settings.query_rewrite_enabled: bool=False`、`settings.query_rewrite_timeout_ms: int=2000`；`QueryOptions{enabled: bool=False, strategy: str="rewrite"}`；`RetrieveRequest.query_options: QueryOptions | None=None`；`QueryProcessingMetadata{...}`；`RetrieveMetadata.query_processing: QueryProcessingMetadata | None=None`。

- [ ] **Step 1: config 追加两项**

`app/core/config.py`，在 rerank 配置附近追加：

```python
    # 提问语义优化：LLM 改写全局默认关，避免所有请求被动调 LLM。
    query_rewrite_enabled: bool = False
    query_rewrite_timeout_ms: int = 2000
```

- [ ] **Step 2: .env.example 追加**

在 `.env.example` LLM 段落后追加：

```
QUERY_REWRITE_ENABLED=false
QUERY_REWRITE_TIMEOUT_MS=2000
```

- [ ] **Step 3: schema 追加 QueryOptions / QueryProcessingMetadata / 字段**

`app/schemas/rag.py`，在 `RetrieveRequest` 上方新增，并给 request/metadata 加字段：

```python
class QueryOptions(BaseModel):
    enabled: bool = False
    strategy: str = "rewrite"


class QueryProcessingMetadata(BaseModel):
    raw_query: str
    effective_query: str
    search_query: str
    rewrite_latency_ms: int = 0
    degraded: bool = False
    degraded_reason: str | None = None
    synonym_applied: bool = False
    synonym_expansions: list[str] = Field(default_factory=list)
```

`RetrieveRequest` 追加：
```python
    # 可选的提问语义优化配置；不传则由全局 QUERY_REWRITE_ENABLED 决定是否改写
    query_options: QueryOptions | None = None
```

`RetrieveMetadata` 追加（放在 rerank 之后）：
```python
    # 提问语义优化链路信息；全无处理时为 None，保持与改前兼容
    query_processing: QueryProcessingMetadata | None = None
```

- [ ] **Step 4: 写测试**

`tests/test_query_schema.py`:

```python
from app.schemas.rag import RetrieveRequest, RetrieveMetadata, QueryOptions


def test_query_options_defaults():
    req = RetrieveRequest(kb_id="k", user_id="u", query="q")
    assert req.query_options is None
    req2 = RetrieveRequest(kb_id="k", user_id="u", query="q", query_options={"enabled": True})
    assert req2.query_options.enabled is True
    assert req2.query_options.strategy == "rewrite"


def test_metadata_query_processing_optional():
    m = RetrieveMetadata(top_k=5, vector_store="pgvector", latency_ms=1,
                         retrieval={"mode": "vector", "degraded": False},
                         rerank={"enabled": False, "degraded": False})
    assert m.query_processing is None
```

- [ ] **Step 5: 跑测试**

Run: `.venv/bin/python -m pytest tests/test_query_schema.py -v`
Expected: PASS

---

### Task 7: RagService 接入 QueryPipeline

**Files:**
- Modify: `app/services/rag_service.py`（构造注入 + retrieve 流程 + 三个私有召回方法用 search_query）
- Modify: `app/models/retrieval_log.py`（可选字段 effective_query / search_query）
- Modify: `app/api/deps.py`（factory 注入 query_pipeline）
- Test: `tests/test_rag_service.py`（追加）

**Interfaces:**
- Consumes: `QueryPipeline`, `QueryProcessResult`, `QueryProcessingMetadata`, `settings.query_rewrite_enabled`
- Produces: `RAGService(..., query_pipeline: QueryPipeline)`；retrieve 用 `qp.search_query` 送三种召回；`RetrieveData.query` 仍是 `req.query`；rerank 仍用 `req.query`；metadata.query_processing 按规则赋值/为 None。

- [ ] **Step 1: retrieval_log 加可选字段**

`app/models/retrieval_log.py`，在 `query` 字段后追加：

```python
    effective_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_query: Mapped[str | None] = mapped_column(Text, nullable=True)
```

> 这两列由 Task 1 之外的迁移覆盖：把它们并入 `migrations/versions/0003_kb_settings.py` 的 upgrade（`op.add_column("retrieval_logs", ...)` ×2）与 downgrade。更新 0003 迁移同时处理这三列。

- [ ] **Step 2: 构造函数注入 query_pipeline**

`app/services/rag_service.py` `__init__` 追加参数与赋值：

```python
        hybrid_search_service: HybridSearchService,
        query_pipeline: "QueryPipeline",
    ):
        ...
        self._hybrid_search = hybrid_search_service
        self._query_pipeline = query_pipeline
```
文件顶部 import：
```python
from app.providers.query.pipeline import QueryPipeline
from app.providers.query.base import QueryProcessResult
from app.schemas.rag import QueryProcessingMetadata
```

- [ ] **Step 3: 写失败测试（追加到 tests/test_rag_service.py）**

先给测试文件的 `_FakeKBRepo.get_for_tenant` 返回带 name/description/settings 的对象（当前返回 dict `{"id","tenant_id"}`）。新增一个 fake pipeline 并断言 search_query 被用于检索、query_processing 正确。

```python
class _FakeKBObj:
    def __init__(self, kb_id, tenant_id, settings=None):
        self.id, self.tenant_id = kb_id, tenant_id
        self.name, self.description = "HR库", "招聘制度"
        self.settings = settings or {}


class _RecordingVectorStore(_FakeVectorStore):
    def __init__(self):
        self.seen_query = None
    async def similarity_search(self, query_vector, *, tenant_id, kb_id, top_k=5):
        return await super().similarity_search(query_vector, tenant_id=tenant_id, kb_id=kb_id, top_k=top_k)


@pytest.mark.asyncio
async def test_retrieve_uses_search_query_and_reports_processing(monkeypatch):
    # kb 带 synonyms；rewrite 关闭时词表仍应生效，query_processing 非空
    kb_settings = {"synonyms": [{"terms": ["背调"], "expand": ["背景调查"]}]}
    svc = _build_service_with_kb(_FakeKBObj("kb-1", "t1", kb_settings))  # helper 见下
    from app.schemas.rag import RetrieveRequest
    data = await svc.retrieve(RetrieveRequest(kb_id="kb-1", user_id="u", query="背调要问啥"), "t1")
    assert data.query == "背调要问啥"                       # 原始 query 不变
    assert data.metadata.query_processing is not None
    assert data.metadata.query_processing.synonym_applied is True
    assert "背景调查" in data.metadata.query_processing.search_query


@pytest.mark.asyncio
async def test_retrieve_no_processing_returns_null():
    svc = _build_service_with_kb(_FakeKBObj("kb-1", "t1", {}))
    from app.schemas.rag import RetrieveRequest
    data = await svc.retrieve(RetrieveRequest(kb_id="kb-1", user_id="u", query="普通问题"), "t1")
    assert data.metadata.query_processing is None
```

> `_build_service_with_kb` 是测试内 helper：构造 `RAGService` 时用返回该 kb 对象的 `_FakeKBRepo`、`_FakeVectorStore`、`_NoopRerank`、以及 `QueryPipeline(_FakeLLM(...))`。参考文件现有 `svc = RAGService(...)` 段落（约 line 116/147/180）复制装配，补 `query_pipeline=QueryPipeline(_FakeLLM(ret={"rewritten_query":"x"}))`。默认 `settings.query_rewrite_enabled=False`，故不会真正调用 LLM。

- [ ] **Step 4: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_rag_service.py -k search_query -v`
Expected: FAIL（构造缺 query_pipeline / 逻辑未接）

- [ ] **Step 5: 在 retrieve 中接 pipeline**

`app/services/rag_service.py` `retrieve()`，在 kb 校验通过之后、`_resolve_retrieval_mode` 附近之前插入：

```python
        kb = await self._kb_repo.get_for_tenant(req.kb_id, tenant_id)
        if kb is None:
            raise KnowledgeBaseNotFound(req.kb_id)

        # 提问语义优化：请求级 query_options 优先于全局 QUERY_REWRITE_ENABLED
        rewrite_enabled = (
            req.query_options.enabled
            if req.query_options is not None
            else settings.query_rewrite_enabled
        )
        qp = await self._query_pipeline.run(
            req.query,
            rewrite_enabled=rewrite_enabled,
            kb_name=getattr(kb, "name", ""),
            kb_description=getattr(kb, "description", None),
            kb_settings=getattr(kb, "settings", {}) or {},
        )
        search_query = qp.search_query
```

- [ ] **Step 6: 三个私有召回方法改用 search_query**

`_retrieve_vector_only`、`_retrieve_bm25_only`、`_retrieve_hybrid` 里所有 `req.query`（送 embedding / keyword_search 的入参）改为传入的 `search_query`。做法：给这三个方法增加 `search_query: str` 形参，retrieve 调用处传 `search_query`；方法体内 `self._embedding.embed_query(req.query)` → `embed_query(search_query)`，`keyword_search(query=req.query...)` → `query=search_query`。**rerank 仍用 `req.query`，不改。**

调用处：
```python
        if retrieval_mode == "vector":
            candidates, retrieval_meta = await self._retrieve_vector_only(req, tenant_id, top_k, search_query)
        elif retrieval_mode == "bm25":
            candidates, retrieval_meta = await self._retrieve_bm25_only(req, tenant_id, top_k, search_query)
        else:
            candidates, retrieval_meta = await self._retrieve_hybrid(req, tenant_id, search_query)
```

- [ ] **Step 7: 组装 query_processing（含 null 规则）+ 日志字段**

`RetrieveMetadata(...)` 构造追加 `query_processing`：

```python
        # 开了改写、词表命中，或 search_query != raw_query 时返回；全无处理时 None
        processed = (
            qp.strategy == "rewrite"
            or qp.synonym_applied
            or qp.search_query != qp.raw_query
            or qp.degraded
        )
        query_processing = (
            QueryProcessingMetadata(
                raw_query=qp.raw_query,
                effective_query=qp.effective_query,
                search_query=qp.search_query,
                rewrite_latency_ms=qp.rewrite_latency_ms,
                degraded=qp.degraded,
                degraded_reason=qp.degraded_reason,
                synonym_applied=qp.synonym_applied,
                synonym_expansions=qp.synonym_expansions,
            )
            if processed
            else None
        )
```
把它传入 `RetrieveMetadata(..., query_processing=query_processing)`。
`RetrievalLog(...)` 追加 `effective_query=qp.effective_query, search_query=qp.search_query`。

- [ ] **Step 8: factory 注入**

`app/api/deps.py` `get_rag_service` 追加依赖与传参：

```python
    llm_provider: LLMProvider = Depends(get_llm_provider),
    ...
    return RAGService(
        ...
        hybrid_search_service=hybrid_search,
        query_pipeline=QueryPipeline(llm_provider),
    )
```
文件顶部 import `from app.providers.query.pipeline import QueryPipeline`（`get_llm_provider` 已存在）。

- [ ] **Step 9: 跑测试**

Run: `.venv/bin/python -m pytest tests/test_rag_service.py -v`
Expected: PASS（新增用例 + 原有用例全绿；原有用例可能需在装配处补 `query_pipeline=` 参数）

- [ ] **Step 10: 全量后端回归**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS（全部）

---

### Task 8: 运维脚本 update_kb_settings.py + 示例

**Files:**
- Create: `scripts/update_kb_settings.py`
- Create: `examples/kb_settings.example.json`
- Test: 手动 syntax 校验（对齐现有 scripts 风格，无单测）

**Interfaces:**
- Consumes: `KnowledgeBaseRepository.update_settings`, app 的 config/db session（复用 `scripts/create_api_key.py` 的 session 装配方式）
- Produces: CLI `python scripts/update_kb_settings.py --kb-id <id> --settings-file <path>`；整文件覆盖 settings；kb 不存在报错退出；打印 kb_id + synonyms 组数。

- [ ] **Step 1: 参考现有脚本装配**

Run: `sed -n '1,60p' scripts/create_api_key.py`
Expected: 看到 async main + session 构造模式，据此复用。

- [ ] **Step 2: 写 examples/kb_settings.example.json**

```json
{
  "synonyms": [
    {"terms": ["背调"], "expand": ["背景调查", "标准问题清单"]},
    {"terms": ["薪酬", "薪资", "工资"], "expand": ["职级", "薪酬定级", "定级标准"]}
  ],
  "rewrite_hint": "可选，补充给 LLM 改写 Prompt 的领域说明，例如告知缩写含义"
}
```

- [ ] **Step 3: 写 scripts/update_kb_settings.py**

对齐 `create_api_key.py` 的 argparse + async session 结构：

```python
"""维护 kb 词表配置：整文件覆盖 knowledge_bases.settings。

用法：
    python scripts/update_kb_settings.py --kb-id <kb_id> --settings-file kb_settings.json

注意：本脚本会用 --settings-file 的内容【整体覆盖】该 kb 的 settings 字段，
不做合并。kb 不存在时报错退出。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.db.session import AsyncSessionLocal  # 与 create_api_key.py 保持一致
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository


async def _run(kb_id: str, settings_file: str) -> None:
    with open(settings_file, "r", encoding="utf-8") as f:
        new_settings = json.load(f)
    async with AsyncSessionLocal() as session:
        repo = KnowledgeBaseRepository(session)
        updated = await repo.update_settings(kb_id, new_settings)
        if updated is None:
            print(f"[ERROR] knowledge base not found: {kb_id}", file=sys.stderr)
            sys.exit(1)
        await session.commit()
        groups = len((new_settings or {}).get("synonyms") or [])
        print(f"[OK] updated settings for kb_id={kb_id} | synonyms groups={groups}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Update knowledge base settings (synonyms/rewrite_hint)")
    parser.add_argument("--kb-id", required=True)
    parser.add_argument("--settings-file", required=True)
    args = parser.parse_args()
    asyncio.run(_run(args.kb_id, args.settings_file))


if __name__ == "__main__":
    main()
```

> 若 `create_api_key.py` 用的 session 入口不是 `AsyncSessionLocal`（如 `get_sessionmaker()`），Step 1 已确认，按其实际写法替换 import 与用法。

- [ ] **Step 4: syntax 校验**

Run: `.venv/bin/python -c "import ast; ast.parse(open('scripts/update_kb_settings.py').read()); print('ok')"`
Expected: `ok`

---

### Task 9: 前端 types + service 对齐新字段

**Files:**
- Modify: `frontend/src/types/api.ts`
- Test: `frontend/` typecheck + build

**Interfaces:**
- Produces: `RetrieveRequest.query_options?: { enabled?: boolean; strategy?: string }`；`QueryProcessing` 接口；`RetrieveMetadata.query_processing?: QueryProcessing | null`。

- [ ] **Step 1: types/api.ts — RetrieveRequest 加 query_options**

在 `rerank_options?...` 之后追加：
```typescript
  query_options?: {
    enabled?: boolean;
    strategy?: string;
  };
```

- [ ] **Step 2: 新增 QueryProcessing 接口 + metadata 字段**

在 `RerankMetadata` 之后新增，并给 `RetrieveMetadata` 加字段：
```typescript
export interface QueryProcessing {
  raw_query: string;
  effective_query: string;
  search_query: string;
  rewrite_latency_ms: number;
  degraded: boolean;
  degraded_reason?: string | null;
  synonym_applied: boolean;
  synonym_expansions: string[];
}
```
`RetrieveMetadata` 追加：
```typescript
  query_processing?: QueryProcessing | null;
```

- [ ] **Step 3: typecheck + build**

Run: `cd frontend && npm run typecheck && npm run build`
Expected: 均通过（service `retrieve` 无需改动，payload 透传新字段）

---

### Task 10: 前端调试台 — 改写开关 + 运行摘要展示

**Files:**
- Modify: `frontend/src/pages/retrieve.tsx`
- Test: `frontend/` typecheck + build

**Interfaces:**
- Consumes: `QueryProcessing` 类型, `HelpTooltip`
- Produces: 检索配置区新增「启用 query 改写」勾选（勾选→payload 带 `query_options:{enabled:true,strategy:"rewrite"}`，不勾→不传）；运行摘要展示 query_processing 链路。

- [ ] **Step 1: 加 state + payload**

在 `rerankTopN` state 后加：
```tsx
  const [rewriteEnabled, setRewriteEnabled] = React.useState(false);
```
`onSubmit` 的 payload 末尾追加（不勾选时不传 query_options，保持与改前一致）：
```tsx
      ...(rewriteEnabled ? { query_options: { enabled: true, strategy: "rewrite" } } : {}),
```

- [ ] **Step 2: 配置区加勾选框（放在 rerank Field 之后）**

```tsx
              <Field
                label="query 改写"
                help="用 AI 把口语问题改成更好搜的说法；更慢、消耗 LLM，可对比开关效果。"
              >
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={rewriteEnabled}
                    onChange={(e) => setRewriteEnabled(e.target.checked)}
                  />
                  启用
                </label>
              </Field>
```

- [ ] **Step 3: 运行摘要展示 query_processing**

在 Card 3「运行摘要」的 CardContent 末尾（rerank 那段 div 之后）追加：
```tsx
              {result.metadata.query_processing && (
                <div className="mt-2 space-y-0.5 border-t pt-2">
                  <div>原话：{result.metadata.query_processing.raw_query}</div>
                  <div>实际检索句：{result.metadata.query_processing.effective_query}</div>
                  {result.metadata.query_processing.search_query !==
                    result.metadata.query_processing.effective_query && (
                    <div className="font-medium">
                      最终检索句：{result.metadata.query_processing.search_query}
                    </div>
                  )}
                  <div className="text-muted-foreground">
                    改写耗时 {result.metadata.query_processing.rewrite_latency_ms}ms
                  </div>
                  {result.metadata.query_processing.degraded && (
                    <div className="text-amber-600">改写失败，已用原话检索</div>
                  )}
                  {result.metadata.query_processing.synonym_applied && (
                    <div className="text-muted-foreground">
                      扩展词：{result.metadata.query_processing.synonym_expansions.join("、")}
                    </div>
                  )}
                </div>
              )}
```

- [ ] **Step 4: typecheck + build**

Run: `cd frontend && npm run typecheck && npm run build`
Expected: 均通过

- [ ] **Step 5: 清理 build 产物**

Run: `git checkout -- frontend/tsconfig.tsbuildinfo 2>/dev/null; true`

---

## Self-Review

**Spec coverage:**
- §二 代码结构 → Task 2–5、8 ✓
- §三 QueryProcessResult → Task 2 ✓
- §四 LLM 改写（含 rewrite_hint 拼接、降级、耗时单独计）→ Task 4 ✓
- §五 词表扩展（子串/大小写/去重/多组）→ Task 3 ✓
- §六 Pipeline（rewrite 可选、词表始终跑、请求级优先）→ Task 5 + Task 7 Step 5 ✓
- §七 DB settings JSONB + create 默认 {} + repo → Task 1 ✓
- §八 Schema query_options / query_processing + null 规则 + query 不替换 + rerank 用 req.query → Task 6 + Task 7 ✓
- §九 接入位置（kb 校验后、召回前；不重复查库；search_query 送 vector/bm25；retrieval_logs 加字段）→ Task 7 ✓
- §十 配置 QUERY_REWRITE_ENABLED/TIMEOUT_MS，复用 LLM_* → Task 6 ✓
- §十一 脚本 + examples → Task 8 ✓
- §十二 调试台开关 + HelpTooltip 文案 + 摘要 → Task 10 ✓
- §十三 验收 → 覆盖于各 Task 测试 ✓

**Type consistency:** `QueryProcessResult` 字段 ↔ `QueryProcessingMetadata`(schema) ↔ `QueryProcessing`(ts) 三处字段名一致（raw/effective/search_query、rewrite_latency_ms、degraded[_reason]、synonym_applied、synonym_expansions）。`QueryPipeline.run(rewrite_enabled=...)` 与 Task 7 调用一致。私有召回方法新增 `search_query` 形参在调用处与定义处一致。

**Placeholder scan:** 无 TBD/TODO；每个代码步骤含完整代码。Task 1 Step 5 与 Task 8 Step 3 各给了「若 fixture/入口不同」的明确回退指令，非占位。

**风险点已标注:** 0003 迁移的 down_revision、retrieval_logs 三列并入同一迁移、脚本 session 入口名——均给了确认命令与回退。

