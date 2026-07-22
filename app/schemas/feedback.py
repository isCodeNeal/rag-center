"""检索反馈请求/响应 schemas。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class FeedbackRequest(BaseModel):
    trace_id: str = Field(..., min_length=1, description="Langfuse trace 标识")
    log_id: str | None = Field(default=None, description="retrieval_logs 记录 ID，用于校验租户权限")
    score: int = Field(..., ge=1, le=5, description="用户评分，1～5 分")
    comment: str | None = Field(default=None, max_length=2000, description="可选备注")


class FeedbackData(BaseModel):
    feedback_id: str
    trace_id: str
    log_id: str | None = None
    score: int
