"""RAG 检索请求/响应 schemas。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class RetrieveRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1, max_length=128)
    kb_id: str = Field(..., min_length=1, max_length=64)
    # user_id 由调用方提供；用于记录日志/未来的 ACL
    user_id: str = Field(..., min_length=1, max_length=128)
    query: str = Field(..., min_length=1)
    # 可选的单次请求级 TOP_K 覆盖配置
    top_k: int | None = Field(default=None, ge=1, le=100)


class RetrievedChunk(BaseModel):
    document_id: str
    chunk_id: str
    title: str
    content: str
    score: float


class RetrieveMetadata(BaseModel):
    top_k: int
    vector_store: str


class RetrieveData(BaseModel):
    query: str
    kb_id: str
    retrieved_chunks: list[RetrievedChunk]
    metadata: RetrieveMetadata
