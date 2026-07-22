"""RAG 检索请求/响应 schemas。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.hybrid_search import RetrievalMetadata, RetrievalOptions
from app.schemas.rerank import RerankMetadata, RerankOptions


class QueryOptions(BaseModel):
    """提问语义优化请求级配置。请求级优先于全局 QUERY_REWRITE_ENABLED。"""

    enabled: bool = False
    strategy: str = "rewrite"  # 第一版仅 rewrite；noop 等价于不传


class QueryProcessing(BaseModel):
    """检索前提问语义优化链路的诊断信息（供调试台/日志），非业务核心字段。"""

    raw_query: str
    effective_query: str
    search_query: str
    strategy: str
    rewrite_latency_ms: int
    degraded: bool
    degraded_reason: str | None = None
    synonym_applied: bool
    synonym_expansions: list[str] = Field(default_factory=list)


class RetrieveRequest(BaseModel):
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
    # 可选的提问语义优化配置；不传时行为与改前一致
    query_options: QueryOptions | None = None
    # 检索预设档位；不传时服务端默认 balanced。plan 会校验是否允许该 profile。
    profile: Literal["speed", "balanced", "quality", "custom"] | None = None


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


class TenantPolicy(BaseModel):
    """本次请求生效的套餐策略，供调试台/日志对照。"""

    plan: str
    retrieve_profile: str
    effective_mode: str
    effective_rerank: bool
    effective_query_rewrite: bool


class RetrieveMetadata(BaseModel):
    top_k: int
    vector_store: str
    latency_ms: int
    # 本次检索的唯一标识，与 retrieval_logs 表主键一致
    log_id: str
    # Langfuse trace 标识；Langfuse 未启用时为 null
    trace_id: str | None = None
    retrieval: RetrievalMetadata
    rerank: RerankMetadata
    # 提问语义优化链路；全无处理时为 None，保持与改前兼容
    query_processing: QueryProcessing | None = None
    # 本次生效的套餐策略；未启用套餐能力时为 None
    tenant_policy: TenantPolicy | None = None


class RetrieveData(BaseModel):
    query: str
    kb_id: str
    retrieved_chunks: list[RetrievedChunk]
    metadata: RetrieveMetadata
