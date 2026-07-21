"""知识库请求/响应 schemas。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CreateKnowledgeBaseRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)


class KnowledgeBaseData(BaseModel):
    kb_id: str
    name: str
    tenant_id: str
    created_at: datetime


class KnowledgeTreeDoc(BaseModel):
    document_id: str
    title: str
    status: int
    chunk_count: int
    created_at: datetime


class KnowledgeTreeKb(BaseModel):
    kb_id: str
    name: str
    description: str | None = None
    created_at: datetime
    documents: list[KnowledgeTreeDoc] = Field(default_factory=list)


class KnowledgeTreeTenant(BaseModel):
    tenant_id: str
    knowledge_bases: list[KnowledgeTreeKb] = Field(default_factory=list)
