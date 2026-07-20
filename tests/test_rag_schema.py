"""RAG / rerank schema 单元测试。"""
from __future__ import annotations

from app.schemas.rag import RetrieveRequest, RetrievedChunk


def test_retrieve_request_accepts_optional_rerank_options():
    req = RetrieveRequest(
        tenant_id="tenant_demo",
        kb_id="kb-1",
        user_id="user-1",
        query="退款需要几天内申请？",
        top_k=20,
        rerank_options={"enabled": True, "top_n": 5},
    )
    assert req.rerank_options is not None
    assert req.rerank_options.enabled is True
    assert req.rerank_options.top_n == 5


def test_retrieved_chunk_supports_rerank_score():
    chunk = RetrievedChunk(
        document_id="doc-1",
        chunk_id="chunk-1",
        title="退款政策",
        content="用户可在订单完成后 7 天内申请退款。",
        score=0.86,
        rerank_score=0.95,
    )
    assert chunk.score == 0.86
    assert chunk.rerank_score == 0.95
