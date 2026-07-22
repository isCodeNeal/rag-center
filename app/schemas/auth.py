"""鉴权相关响应 schema。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class AuthMeFeatures(BaseModel):
    allowed_profiles: list[str] = Field(default_factory=list)
    hybrid_allowed: bool
    rerank_allowed: bool
    query_rewrite_allowed: bool


class AuthMeLimits(BaseModel):
    retrieve_qps: int
    retrieve_daily: int
    max_kb: int
    max_documents_per_kb: int
    max_processing_documents: int


class AuthMeUsage(BaseModel):
    kb_count: int
    retrieve_daily_count: int


class AuthMeData(BaseModel):
    tenant_id: str
    tenant_name: str
    key_prefix: str
    key_name: str
    plan: str
    features: AuthMeFeatures
    limits: AuthMeLimits
    usage: AuthMeUsage
