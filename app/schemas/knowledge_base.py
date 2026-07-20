"""知识库请求/响应 schemas。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CreateKnowledgeBaseRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    # tenant_id 由调用方提供（业务上下文）
    tenant_id: str = Field(..., min_length=1, max_length=128)


class KnowledgeBaseData(BaseModel):
    kb_id: str
    name: str
    tenant_id: str
    created_at: datetime
