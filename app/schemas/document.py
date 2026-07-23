"""文档上传请求/响应 schemas。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class UploadDocumentRequest(BaseModel):
    kb_id: str = Field(..., min_length=1, max_length=64)
    title: str = Field(..., min_length=1, max_length=512)
    # 第一阶段直接接受原始文本内容（.txt / .md 风格的纯文本）
    # multipart upload 时 content 为空，此时由 Worker 解析原文件填入
    content: str | None = Field(default=None, min_length=1)
    # 关于来源的可选提示；默认为纯文本
    source_type: str = Field(default="text", max_length=32)


class UploadDocumentData(BaseModel):
    document_id: str
    kb_id: str
    # 1 = SUCCESS（成功）, 2 = FAILED（失败）, 3 = PROCESSING（处理中）
    status: int
    chunk_count: int


class DocumentStatusData(BaseModel):
    """状态查询接口返回；供前端轮询与运维接口复用。"""

    document_id: str
    kb_id: str
    title: str
    # 1 = SUCCESS, 2 = FAILED, 3 = PROCESSING
    status: int
    error_message: str | None = None
    chunk_count: int
    created_at: datetime
    updated_at: datetime
    # 文件上传时的原始文件名；JSON 文本 upload 为 null
    source_filename: str | None = None
    # 来源类型；text / pdf / docx / markdown 等
    source_type: str | None = None
