"""RAG retrieval request/response schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field


class RetrieveRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1, max_length=128)
    kb_id: str = Field(..., min_length=1, max_length=64)
    # user_id is supplied by the caller; recorded for logging / future ACL.
    user_id: str = Field(..., min_length=1, max_length=128)
    query: str = Field(..., min_length=1)
    # Optional per-request override of the configured TOP_K.
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
