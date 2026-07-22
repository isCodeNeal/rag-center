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
    # 索引失败原因；仅 FAILED 时有值，其余为 null
    error_message: str | None = None


class KnowledgeTreeKb(BaseModel):
    kb_id: str
    name: str
    description: str | None = None
    created_at: datetime
    documents: list[KnowledgeTreeDoc] = Field(default_factory=list)


class KnowledgeTreeTenant(BaseModel):
    tenant_id: str
    knowledge_bases: list[KnowledgeTreeKb] = Field(default_factory=list)


class KnowledgeBaseDetailData(BaseModel):
    """单个知识库详情，含完整 settings 词表 JSON，供编辑弹窗预填。"""

    kb_id: str
    name: str
    description: str | None = None
    settings: dict = Field(default_factory=dict)
    document_count: int
    created_at: datetime
    updated_at: datetime


class UpdateKnowledgeBaseRequest(BaseModel):
    """更新知识库；字段均可选，至少传一个。settings 整段替换，非 deep merge。"""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    settings: dict | None = None
