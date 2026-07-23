"""文档接口：异步上传（JSON / multipart 双模式）、状态查询、删除、重试索引。"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import get_document_service, get_quota_service
from app.api.v1.deps import get_current_tenant
from app.core.auth import TenantContext
from app.core.config import settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import raise_error
from app.models.enums import DocumentStatus
from app.schemas.common import ApiResponse
from app.schemas.document import (
    DocumentStatusData,
    UploadDocumentData,
    UploadDocumentRequest,
)
from app.services.document_service import DocumentService
from app.services.quota_service import QuotaService
from app.tasks.indexing import index_document_task
from app.tenant.plan_resolver import resolve_plan
from app.utils.id_generator import new_document_id

router = APIRouter(prefix="/documents", tags=["documents"])

# 允许上传的文件扩展名 -> source_type 映射
_ALLOWED_EXTENSIONS: dict[str, str] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".md": "markdown",
    ".txt": "text",
}


@router.post("/upload", response_model=ApiResponse[UploadDocumentData])
async def upload_document(
    request: Request,
    ctx: TenantContext = Depends(get_current_tenant),
    service: DocumentService = Depends(get_document_service),
    quota: QuotaService = Depends(get_quota_service),
) -> ApiResponse[UploadDocumentData]:
    """支持两种 Content-Type：
    - multipart/form-data: 上传原始文件（pdf/docx/md/txt）
    - application/json:    上传纯文本内容（原有逻辑，零破坏）
    """
    content_type = request.headers.get("content-type", "")

    if "multipart/form-data" in content_type:
        # ---- multipart 模式 ----
        form = await request.form()
        file = form.get("file")
        kb_id = form.get("kb_id")
        title_form = form.get("title")

        if file is None or not hasattr(file, "filename"):
            raise_error(ErrorCode.PARAM_ERROR, msg="multipart 上传必须包含 file 字段")
        if not kb_id:
            raise_error(ErrorCode.PARAM_ERROR, msg="multipart 上传必须包含 kb_id 字段")

        filename: str = file.filename or ""
        suffix = Path(filename).suffix.lower()
        if suffix not in _ALLOWED_EXTENSIONS:
            raise_error(
                ErrorCode.PARAM_ERROR,
                msg=f"不支持的文件类型 {suffix!r}，允许：{', '.join(_ALLOWED_EXTENSIONS)}",
            )

        # 文件大小校验（读取全部内容到内存后检查）
        file_bytes: bytes = await file.read()
        max_bytes = settings.document_max_size_mb * 1024 * 1024
        if len(file_bytes) > max_bytes:
            raise_error(
                ErrorCode.PARAM_ERROR,
                msg=f"文件大小超过限制（最大 {settings.document_max_size_mb} MB）",
            )

        # 配额检查
        await quota.check_can_upload(ctx.tenant_id, str(kb_id), resolve_plan(ctx.plan))

        # 计算存盘路径：{storage_root}/{tenant_id}/{document_id}/{filename}
        document_id = new_document_id()
        title = str(title_form) if title_form else Path(filename).stem
        source_type = _ALLOWED_EXTENSIONS[suffix]

        storage_dir = Path(settings.document_storage_path) / ctx.tenant_id / document_id
        storage_dir.mkdir(parents=True, exist_ok=True)
        file_path = storage_dir / filename
        file_path.write_bytes(file_bytes)

        document = await service.create_document_record(
            None,
            ctx.tenant_id,
            file_path=str(file_path),
            source_filename=filename,
            source_type_override=source_type,
            title_override=title,
            kb_id_override=str(kb_id),
        )
    else:
        # ---- JSON 模式（原有逻辑，零破坏）----
        body = await request.json()
        req = UploadDocumentRequest(**body)
        await quota.check_can_upload(ctx.tenant_id, req.kb_id, resolve_plan(ctx.plan))
        document = await service.create_document_record(req, ctx.tenant_id)

    index_document_task.delay(document.id)
    return ApiResponse.success(
        UploadDocumentData(
            document_id=document.id,
            kb_id=document.kb_id,
            status=DocumentStatus.PROCESSING.value,
            chunk_count=0,
        )
    )


@router.get("/{document_id}", response_model=ApiResponse[DocumentStatusData])
async def get_document_status(
    document_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
    service: DocumentService = Depends(get_document_service),
) -> ApiResponse[DocumentStatusData]:
    data = await service.get_status(document_id, ctx.tenant_id)
    return ApiResponse.success(data)


@router.delete("/{document_id}", response_model=ApiResponse[None])
async def delete_document(
    document_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
    service: DocumentService = Depends(get_document_service),
) -> ApiResponse[None]:
    await service.delete_document(document_id, ctx.tenant_id)
    return ApiResponse.success(None)


@router.post("/{document_id}/reindex", response_model=ApiResponse[DocumentStatusData])
async def reindex_document(
    document_id: str,
    reparse: bool = Query(default=False, description="重新从原文件解析（需 source_file_path 存在）"),
    ctx: TenantContext = Depends(get_current_tenant),
    service: DocumentService = Depends(get_document_service),
    quota: QuotaService = Depends(get_quota_service),
) -> ApiResponse[DocumentStatusData]:
    # 并发 PROCESSING 配额检查（reindex 会新占一个索引名额）
    await quota.check_processing_capacity(ctx.tenant_id, resolve_plan(ctx.plan))
    data = await service.reindex(document_id, ctx.tenant_id, reparse=reparse)
    index_document_task.delay(document_id)
    return ApiResponse.success(data)
