"""RAGService 的单元测试（无需真实数据库 / embedding / 向量库 / 大模型）。"""
from __future__ import annotations

import pytest

from app.providers.embedding.base import EmbeddingProvider
from app.providers.rerank.base import RerankProvider
from app.providers.vectorstores.base import VectorStore
from app.schemas.rag import RetrieveRequest
from app.providers.query.pipeline import QueryPipeline
from app.services.rag_service import RAGService


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


class _FakeKB:
    def __init__(self, kb_id: str, tenant_id: str):
        self.id = kb_id
        self.tenant_id = tenant_id
        self.name = "退款政策库"
        self.description = "电商售后相关制度"
        self.settings: dict = {}


class _FakeKBRepo:
    async def get_for_tenant(self, kb_id: str, tenant_id: str):
        return _FakeKB(kb_id, tenant_id)


class _FakeLLM:
    """改写默认关闭，pipeline 不会调用它；仅为构造 QueryPipeline 占位。"""

    async def chat_json(self, *args, **kwargs):
        raise AssertionError("LLM should not be called when rewrite is disabled")


class _FakeLogRepo:
    def __init__(self):
        self.logs = []

    async def create(self, log):
        self.logs.append(log)
        return log


class _FakeSession:
    async def commit(self):
        return None


class _FakeVectorStore(VectorStore):
    async def add_chunks(self, chunks):
        return None

    async def similarity_search(self, query_vector, *, tenant_id: str, kb_id: str, top_k: int = 5):
        return [
            {
                "document_id": "doc-1",
                "chunk_id": "chunk-1",
                "title": "退款政策",
                "content": "用户可在订单完成后 7 天内申请退款。",
                "score": 0.86,
            },
            {
                "document_id": "doc-1",
                "chunk_id": "chunk-2",
                "title": "退款政策",
                "content": "特殊商品不支持无理由退款。",
                "score": 0.73,
            },
        ][:top_k]

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


class _GoodRerank(RerankProvider):
    @property
    def name(self) -> str:
        return "llm"

    async def rerank(self, *, query: str, chunks: list[dict], top_n: int) -> list[dict]:
        out = []
        for c in chunks:
            item = dict(c)
            item["rerank_score"] = 0.9 if c["chunk_id"] == "chunk-2" else 0.3
            out.append(item)
        out.sort(key=lambda x: x["rerank_score"], reverse=True)
        return out[:top_n]


class _FailingRerank(RerankProvider):
    @property
    def name(self) -> str:
        return "llm"

    async def rerank(self, *, query: str, chunks: list[dict], top_n: int) -> list[dict]:
        from app.core.exceptions import RerankError

        raise RerankError("json parse failed")


@pytest.mark.asyncio
async def test_rag_service_without_rerank_returns_vector_hits():
    svc = RAGService(
        _FakeSession(),
        kb_repository=_FakeKBRepo(),
        retrieval_log_repository=_FakeLogRepo(),
        embedding_provider=_FakeEmbedding(),
        vector_store=_FakeVectorStore(),
        vector_store_name="pgvector",
        keyword_search_provider=None,
        keyword_search_provider_name=None,
        rerank_provider=_NoopRerank(),
        hybrid_search_service=None,  # type: ignore
        query_pipeline=QueryPipeline(_FakeLLM()),
    )
    data = await svc.retrieve(
        RetrieveRequest(
            kb_id="kb-1",
            user_id="u-1",
            query="退款需要几天内申请？",
            rerank_options={"enabled": False, "top_n": 1},
            profile="custom",
        ),
        "tenant_demo",
        "pro",
    )
    assert len(data.retrieved_chunks) == 1
    assert data.retrieved_chunks[0].chunk_id == "chunk-1"
    assert data.retrieved_chunks[0].rerank_score is None
    assert data.metadata.rerank.enabled is False
    assert isinstance(data.metadata.latency_ms, int)
    assert data.metadata.latency_ms >= 0


@pytest.mark.asyncio
async def test_rag_service_with_rerank_returns_rerank_score_and_metadata():
    svc = RAGService(
        _FakeSession(),
        kb_repository=_FakeKBRepo(),
        retrieval_log_repository=_FakeLogRepo(),
        embedding_provider=_FakeEmbedding(),
        vector_store=_FakeVectorStore(),
        vector_store_name="pgvector",
        keyword_search_provider=None,
        keyword_search_provider_name=None,
        rerank_provider=_GoodRerank(),
        hybrid_search_service=None,  # type: ignore
        query_pipeline=QueryPipeline(_FakeLLM()),
    )
    data = await svc.retrieve(
        RetrieveRequest(
            kb_id="kb-1",
            user_id="u-1",
            query="退款需要几天内申请？",
            top_k=2,
            rerank_options={"enabled": True, "top_n": 1},
            profile="custom",
        ),
        "tenant_demo",
        "pro",
    )
    assert len(data.retrieved_chunks) == 1
    assert data.retrieved_chunks[0].chunk_id == "chunk-2"
    assert data.retrieved_chunks[0].score == 0.73
    assert data.retrieved_chunks[0].rerank_score == 0.9
    assert data.metadata.rerank.enabled is True
    assert data.metadata.rerank.provider == "llm"
    assert data.metadata.rerank.top_n == 1


@pytest.mark.asyncio
async def test_rag_service_rerank_failure_degrades_to_vector_order():
    svc = RAGService(
        _FakeSession(),
        kb_repository=_FakeKBRepo(),
        retrieval_log_repository=_FakeLogRepo(),
        embedding_provider=_FakeEmbedding(),
        vector_store=_FakeVectorStore(),
        vector_store_name="pgvector",
        keyword_search_provider=None,
        keyword_search_provider_name=None,
        rerank_provider=_FailingRerank(),
        hybrid_search_service=None,  # type: ignore
        query_pipeline=QueryPipeline(_FakeLLM()),
    )
    data = await svc.retrieve(
        RetrieveRequest(
            kb_id="kb-1",
            user_id="u-1",
            query="退款需要几天内申请？",
            top_k=2,
            rerank_options={"enabled": True, "top_n": 1},
            profile="custom",
        ),
        "tenant_demo",
        "pro",
    )
    assert len(data.retrieved_chunks) == 1
    # 降级后沿用原向量排序
    assert data.retrieved_chunks[0].chunk_id == "chunk-1"
    assert data.retrieved_chunks[0].rerank_score is None
    assert data.metadata.rerank.enabled is True
    assert data.metadata.rerank.degraded is True
    assert "json parse failed" in (data.metadata.rerank.error or "")
