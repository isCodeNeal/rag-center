"""RAG 检索请求/响应 schemas。"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.hybrid_search import RetrievalMetadata, RetrievalOptions
from app.schemas.rerank import RerankMetadata, RerankOptions


class RetrieveRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1, max_length=128)
    kb_id: str = Field(..., min_length=1, max_length=64)
    # user_id 由调用方提供；用于记录日志/未来的 ACL
    user_id: str = Field(..., min_length=1, max_length=128)
    query: str = Field(..., min_length=1)
    # 可选的单次请求级 TOP_K 覆盖配置（向量召回候选数量；启用 rerank 时建议大于 top_n）
    top_k: int | None = Field(default=None, ge=1, le=100)
    # 可选的单次请求级检索配置（检索模式、混合检索 top_k 等）
    retrieval_options: RetrievalOptions | None = None
    # 可选的单次请求级 rerank 配置；不传则完全由 .env 系统配置决定
    rerank_options: RerankOptions | None = None


class RetrievedChunk(BaseModel):
    document_id: str
    chunk_id: str
    title: str
    content: str
    score: float
    # 混合检索相关字段（未启用时为 None）
    vector_score: float | None = None
    bm25_score: float | None = None
    vector_rank: int | None = None
    bm25_rank: int | None = None
    retrieval_source: str | None = None  # vector / bm25 / hybrid
    # 大模型重排分数；未启用 rerank 时为 None
    rerank_score: float | None = None


class RetrieveMetadata(BaseModel):
    top_k: int
    vector_store: str
    retrieval: RetrievalMetadata
    rerank: RerankMetadata


class RetrieveData(BaseModel):
    query: str
    kb_id: str
    retrieved_chunks: list[RetrievedChunk]
    metadata: RetrieveMetadata
