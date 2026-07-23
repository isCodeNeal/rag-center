"""混合检索相关 schemas。

覆盖三类数据：
1. `RetrievalOptions` —— 请求体中可选的单次请求级检索配置（mode / vector_top_k / bm25_top_k / rrf_k）。
2. `RetrievalMetadata` —— 返回给业务方的检索元信息，嵌入响应 `metadata.retrieval`。
3. 内部融合结构（用于 HybridSearchService RRF 融合逻辑）。

注意：候选 chunk 在 provider/service 内部仍以 `list[dict]` 形式传递（与既有
向量库风格保持一致），这里的 schema 只负责「请求校验」和「对外响应元信息」。
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class RetrievalOptions(BaseModel):
    """请求体中可选的 retrieval_options，用于单次请求覆盖 .env 的全局检索模式。"""

    mode: str | None = Field(default=None, description="检索模式：vector / bm25 / hybrid；不传则使用系统配置")
    vector_top_k: int | None = Field(default=None, ge=1, le=100, description="hybrid 模式下向量召回数量")
    bm25_top_k: int | None = Field(default=None, ge=1, le=100, description="hybrid 模式下 BM25 召回数量")
    rrf_k: int | None = Field(default=None, ge=1, le=200, description="RRF 融合参数，默认 60")


class RetrievalMetadata(BaseModel):
    """返回给业务方的检索元信息，嵌入 RetrieveMetadata.retrieval。"""

    mode: str
    fusion: str | None = None  # hybrid 模式下才有，第一版只支持 "rrf"
    rrf_k: int | None = None
    vector_store: str | None = None
    keyword_search: str | None = None
    vector_top_k: int | None = None
    bm25_top_k: int | None = None
    vector_count: int | None = None  # 实际向量召回数量
    bm25_count: int | None = None  # 实际 BM25 召回数量
    fused_count: int | None = None  # RRF 融合后总数（去重）
    # hybrid 模式下 BM25 失败降级为纯向量时置为 True
    degraded: bool = False
    degraded_reason: str | None = None
    # 多库并行召回时的扩展字段
    multi_kb: bool = False
    kb_count: int | None = None
    per_kb_top_k: int | None = None
    # 多库 partial 容错时的失败库列表
    failed_kb_ids: list[str] | None = None
    partial_kb_success: bool = False
    # 空结果原因
    empty_reason: str | None = None  # "no_indexed_chunks" | "no_chunks_matched"
