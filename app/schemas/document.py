"""文档上传请求/响应 schemas。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class UploadDocumentRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1, max_length=128)
    kb_id: str = Field(..., min_length=1, max_length=64)
    title: str = Field(..., min_length=1, max_length=512)
    # 第一阶段直接接受原始文本内容（.txt / .md 风格的纯文本）
    content: str = Field(..., min_length=1)
    # 关于来源的可选提示；默认为纯文本
    source_type: str = Field(default="text", max_length=32)


class UploadDocumentData(BaseModel):
    document_id: str
    kb_id: str
    # 1 = SUCCESS（成功）, 2 = FAILED（失败）, 3 = PROCESSING（处理中）
    status: int
    chunk_count: int
