"""检索链路健壮性单测。

覆盖 8 个场景：
1. vector 失败 → hybrid 降级为 BM25，metadata.retrieval.degraded=True，degraded_reason 含 "vector"
2. BM25 失败 → hybrid 降级为 vector，degraded=True，degraded_reason 含 "bm25"
3. 双路都失败 → raise AppException(VECTOR_STORE_ERROR)
4. 多库一库失败 → 另一库 chunk 仍返回，failed_kb_ids 非空，partial_kb_success=True
5. 多库全部失败 → raise AppException(VECTOR_STORE_ERROR)
6. 空 query → ValidationError（schema 层）
7. 超长 query → AppException(PARAM_ERROR)（service 层）
8. happy path 单库 balanced → 正常返回，无 degraded
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from pydantic import ValidationError

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException, KeywordSearchError
from app.providers.embedding.base import EmbeddingProvider
from app.providers.keyword_search.base import KeywordSearchProvider
from app.providers.query.pipeline import QueryPipeline
from app.providers.rerank.base import RerankProvider
from app.providers.vectorstores.base import VectorStore
from app.schemas.rag import RetrieveRequest
from app.services.rag_service import RAGService
from app.services.hybrid_search_service import HybridSearchService


# ---------------------------------------------------------------------------
# 辅助 fakes
# ---------------------------------------------------------------------------

class _FakeEmbedding(EmbeddingProvider):
    @property
    def model(self) -> str:
        return "fake-embedding"

    @property
    def dimension(self) -> int:
        return 3

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]

    async def embed_query(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]


class _FailingEmbedding(EmbeddingProvider):
    @property
    def model(self) -> str:
        return "failing-embedding"

    @property
    def dimension(self) -> int:
        return 3

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise Exception("embedding service down")

    async def embed_query(self, text: str) -> list[float]:
        raise Exception("embedding service down")


class _FakeVectorStore(VectorStore):
    def __init__(self, hits: list[dict] | None = None):
        self._hits = hits or [
            {
                "document_id": "doc-1",
                "chunk_id": "chunk-1",
                "title": "退款政策",
                "content": "7天内可申请退款",
                "score": 0.9,
            }
        ]

    async def add_chunks(self, chunks):
        return None

    async def similarity_search(self, query_vector, *, tenant_id: str, kb_id: str, top_k: int = 5):
        return self._hits[:top_k]

    async def delete_by_document_id(self, document_id: str):
        return None


class _FailingVectorStore(VectorStore):
    async def add_chunks(self, chunks):
        return None

    async def similarity_search(self, query_vector, *, tenant_id: str, kb_id: str, top_k: int = 5):
        raise Exception("vector store down")

    async def delete_by_document_id(self, document_id: str):
        return None


class _FakeKeywordSearch(KeywordSearchProvider):
    def __init__(self, hits: list[dict] | None = None):
        self._hits = hits or [
            {
                "document_id": "doc-1",
                "chunk_id": "chunk-bm25-1",
                "title": "退款政策",
                "content": "BM25 退款内容",
                "bm25_score": 0.8,
            }
        ]

    async def add_chunks(self, chunks):
        return None

    async def keyword_search(self, *, query: str, tenant_id: str, kb_id: str, top_k: int = 20):
        return self._hits[:top_k]

    async def delete_by_document_id(self, document_id: str):
        return None


class _FailingKeywordSearch(KeywordSearchProvider):
    async def add_chunks(self, chunks):
        return None

    async def keyword_search(self, *, query: str, tenant_id: str, kb_id: str, top_k: int = 20):
        raise KeywordSearchError("ES down")

    async def delete_by_document_id(self, document_id: str):
        return None


class _NoopRerank(RerankProvider):
    @property
    def name(self) -> str:
        return "noop"

    async def rerank(self, *, query: str, chunks: list[dict], top_n: int) -> list[dict]:
        out = []
        for c in chunks[:top_n]:
            item = dict(c)
            item["rerank_score"] = None
            out.append(item)
        return out


class _FakeKB:
    def __init__(self, kb_id: str):
        self.id = kb_id
        self.tenant_id = "tenant_demo"
        self.name = f"TestKB-{kb_id}"
        self.description = "测试知识库"
        self.settings: dict = {}


class _FakeKBRepo:
    async def get_for_tenant(self, kb_id: str, tenant_id: str):
        return _FakeKB(kb_id)


class _FakeLogRepo:
    async def create(self, log):
        return log


class _FakeSession:
    async def commit(self):
        return None


class _FakeHybridSearch:
    """RRF 融合：直接拼接两路结果，按 bm25_score/score 降序，取 top_n。"""

    def fuse_rrf(
        self,
        *,
        vector_chunks: list[dict],
        bm25_chunks: list[dict],
        top_n: int,
    ) -> list[dict]:
        fused = []
        for rank, chunk in enumerate(vector_chunks, start=1):
            c = dict(chunk)
            c["vector_rank"] = rank
            c["bm25_rank"] = None
            c["retrieval_source"] = "vector"
            fused.append(c)
        for rank, chunk in enumerate(bm25_chunks, start=1):
            c = dict(chunk)
            c["bm25_rank"] = rank
            c["vector_rank"] = None
            c["score"] = chunk.get("bm25_score", 0.0)
            c["retrieval_source"] = "bm25"
            fused.append(c)
        return fused[:top_n]


class _FakeLLM:
    async def chat_json(self, *args, **kwargs):
        raise AssertionError("LLM should not be called")


def make_rag_service(
    *,
    embedding_provider: EmbeddingProvider | None = None,
    vector_store: VectorStore | None = None,
    keyword_search_provider: KeywordSearchProvider | None = None,
    hybrid_search_service: HybridSearchService | None = None,
    kb_repo=None,
    log_repo=None,
    session=None,
) -> RAGService:
    """辅助函数：构造 RAGService，参数允许部分覆盖，其余用默认 fake。"""
    return RAGService(
        session or _FakeSession(),
        kb_repository=kb_repo or _FakeKBRepo(),
        retrieval_log_repository=log_repo or _FakeLogRepo(),
        embedding_provider=embedding_provider or _FakeEmbedding(),
        vector_store=vector_store or _FakeVectorStore(),
        vector_store_name="pgvector",
        keyword_search_provider=keyword_search_provider,
        keyword_search_provider_name="elasticsearch" if keyword_search_provider else None,
        rerank_provider=_NoopRerank(),
        hybrid_search_service=hybrid_search_service or _FakeHybridSearch(),  # type: ignore
        query_pipeline=QueryPipeline(_FakeLLM()),
    )


def _hybrid_request(kb_id: str = "kb-1", query: str = "退款政策") -> RetrieveRequest:
    """构造一个 hybrid 模式的检索请求。"""
    return RetrieveRequest(
        kb_id=kb_id,
        user_id="u-test",
        query=query,
        retrieval_options={"mode": "hybrid"},
        rerank_options={"enabled": False},
        profile="custom",
    )


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hybrid_vector_failed_degrades_to_bm25():
    """场景 1：向量失败（embed_query 抛异常）→ 降级为纯 BM25 结果。"""
    svc = make_rag_service(
        embedding_provider=_FailingEmbedding(),
        keyword_search_provider=_FakeKeywordSearch(),
    )
    data = await svc.retrieve(_hybrid_request(), "tenant_demo", "pro")

    assert len(data.retrieved_chunks) > 0
    retrieval = data.metadata.retrieval
    assert retrieval.degraded is True
    assert "vector" in (retrieval.degraded_reason or "")
    # 所有 chunk 来源应为 bm25
    for chunk in data.retrieved_chunks:
        assert chunk.retrieval_source == "bm25"


@pytest.mark.asyncio
async def test_hybrid_bm25_failed_degrades_to_vector():
    """场景 2：BM25 失败（KeywordSearchError）→ 降级为纯向量结果（回归）。"""
    svc = make_rag_service(
        keyword_search_provider=_FailingKeywordSearch(),
    )
    data = await svc.retrieve(_hybrid_request(), "tenant_demo", "pro")

    assert len(data.retrieved_chunks) > 0
    retrieval = data.metadata.retrieval
    assert retrieval.degraded is True
    assert "bm25" in (retrieval.degraded_reason or "")
    for chunk in data.retrieved_chunks:
        assert chunk.retrieval_source == "vector"


@pytest.mark.asyncio
async def test_hybrid_both_failed_raises_error():
    """场景 3：向量 + BM25 双路都失败 → 抛 AppException(VECTOR_STORE_ERROR)。"""
    svc = make_rag_service(
        embedding_provider=_FailingEmbedding(),
        keyword_search_provider=_FailingKeywordSearch(),
    )
    with pytest.raises(AppException) as exc_info:
        await svc.retrieve(_hybrid_request(), "tenant_demo", "pro")

    assert exc_info.value.error_code == ErrorCode.VECTOR_STORE_ERROR


@pytest.mark.asyncio
async def test_multi_kb_one_failed_partial_success():
    """场景 4：多库一库失败 → 另一库结果仍返回，failed_kb_ids 非空，partial_kb_success=True。"""

    class _PartialKBRepo:
        async def get_for_tenant(self, kb_id: str, tenant_id: str):
            return _FakeKB(kb_id)

    # kb-1 vector search 正常，kb-2 vector search 会失败
    # 用 vector 模式（不需要 keyword search）
    call_count = {"n": 0}

    class _PartialVectorStore(VectorStore):
        async def add_chunks(self, chunks):
            return None

        async def similarity_search(self, query_vector, *, tenant_id: str, kb_id: str, top_k: int = 5):
            call_count["n"] += 1
            if kb_id == "kb-2":
                raise Exception("kb-2 vector store error")
            return [
                {
                    "document_id": "doc-1",
                    "chunk_id": "chunk-kb1-1",
                    "title": "KB1 chunk",
                    "content": "content",
                    "score": 0.9,
                }
            ]

        async def delete_by_document_id(self, document_id: str):
            return None

    svc = make_rag_service(
        vector_store=_PartialVectorStore(),
        kb_repo=_PartialKBRepo(),
    )
    req = RetrieveRequest(
        kb_ids=["kb-1", "kb-2"],
        user_id="u-test",
        query="退款",
        retrieval_options={"mode": "vector"},
        rerank_options={"enabled": False},
        profile="custom",
    )
    data = await svc.retrieve(req, "tenant_demo", "pro")

    assert len(data.retrieved_chunks) > 0
    retrieval = data.metadata.retrieval
    assert retrieval.failed_kb_ids == ["kb-2"]
    assert retrieval.partial_kb_success is True
    assert retrieval.degraded is True


@pytest.mark.asyncio
async def test_multi_kb_all_failed_raises_error():
    """场景 5：多库全部失败 → 抛 AppException(VECTOR_STORE_ERROR)。"""

    class _AlwaysFailVectorStore(VectorStore):
        async def add_chunks(self, chunks):
            return None

        async def similarity_search(self, query_vector, *, tenant_id: str, kb_id: str, top_k: int = 5):
            raise Exception("all vector stores down")

        async def delete_by_document_id(self, document_id: str):
            return None

    svc = make_rag_service(
        vector_store=_AlwaysFailVectorStore(),
    )
    req = RetrieveRequest(
        kb_ids=["kb-1", "kb-2"],
        user_id="u-test",
        query="退款",
        retrieval_options={"mode": "vector"},
        rerank_options={"enabled": False},
        profile="custom",
    )
    with pytest.raises(AppException) as exc_info:
        await svc.retrieve(req, "tenant_demo", "pro")

    assert exc_info.value.error_code == ErrorCode.VECTOR_STORE_ERROR


def test_empty_query_raises_validation_error():
    """场景 6：空/纯空白 query → Pydantic ValidationError（schema 层）。"""
    # 空字符串（min_length=1 校验）
    with pytest.raises(ValidationError):
        RetrieveRequest(kb_id="kb-1", user_id="u-test", query="")

    # 纯空白字符（field_validator 校验）
    with pytest.raises(ValidationError):
        RetrieveRequest(kb_id="kb-1", user_id="u-test", query="   ")


@pytest.mark.asyncio
async def test_query_too_long_raises_param_error():
    """场景 7：超长 query → AppException(PARAM_ERROR)（service 层）。"""
    svc = make_rag_service()
    long_query = "x" * 2001  # 超过默认 2000 上限

    req = RetrieveRequest(
        kb_id="kb-1",
        user_id="u-test",
        query=long_query,
        rerank_options={"enabled": False},
        profile="custom",
    )

    with patch("app.services.rag_service.settings") as mock_settings:
        mock_settings.query_max_length = 2000
        mock_settings.multi_kb_max = 5
        mock_settings.hybrid_vector_top_k = 20
        mock_settings.hybrid_bm25_top_k = 20
        mock_settings.hybrid_rrf_k = 60
        mock_settings.hybrid_top_n = 20
        mock_settings.top_k = 5
        mock_settings.rerank_top_n = 5
        mock_settings.rerank_max_candidates = 20
        mock_settings.retrieval_mode = "vector"
        mock_settings.rerank_enabled = False
        mock_settings.query_rewrite_enabled = False

        with pytest.raises(AppException) as exc_info:
            await svc.retrieve(req, "tenant_demo", "pro")

    assert exc_info.value.error_code == ErrorCode.PARAM_ERROR
    assert "过长" in exc_info.value.msg


@pytest.mark.asyncio
async def test_happy_path_single_kb_balanced():
    """场景 8：单库 balanced（hybrid 模式）正常返回，无 degraded。"""
    svc = make_rag_service(
        keyword_search_provider=_FakeKeywordSearch(),
    )
    req = RetrieveRequest(
        kb_id="kb-1",
        user_id="u-test",
        query="退款政策",
        rerank_options={"enabled": False},
        profile="balanced",
    )
    data = await svc.retrieve(req, "tenant_demo", "pro")

    assert len(data.retrieved_chunks) > 0
    assert data.metadata.retrieval.degraded is False
    assert data.metadata.retrieval.empty_reason is None
    assert data.metadata.rerank.enabled is False
