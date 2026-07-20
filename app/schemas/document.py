"""Document upload request/response schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field


class UploadDocumentRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1, max_length=128)
    kb_id: str = Field(..., min_length=1, max_length=64)
    title: str = Field(..., min_length=1, max_length=512)
    # Stage 1 accepts raw text content directly (.txt / .md style plain text).
    content: str = Field(..., min_length=1)
    # Optional hint about the source; defaults to plain text.
    source_type: str = Field(default="text", max_length=32)


class UploadDocumentData(BaseModel):
    document_id: str
    kb_id: str
    # 1 = SUCCESS, 2 = FAILED, 3 = PROCESSING
    status: int
    chunk_count: int
