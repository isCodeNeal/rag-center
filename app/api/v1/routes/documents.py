"""文档接口：异步上传、状态查询、删除、重试索引。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_document_service, get_quota_service
from app.api.v1.deps import get_current_tenant
from app.core.auth import TenantContext
from app.models.enums import DocumentStatus
from app.schemas.common import ApiResponse
from app.schemas.document import (
    DocumentStatusData,
    UploadDocumentData,
    UploadDocumentRequest,
)
from app.services.document_service import DocumentService
from app.services.quota_service import QuotaService
from app.tenant.plan_resolver import resolve_plan
from app.tasks.indexing import index_document_task

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=ApiResponse[UploadDocumentData])
async def upload_document(
    req: UploadDocumentRequest,
    ctx: TenantContext = Depends(get_current_tenant),
    service: DocumentService = Depends(get_document_service),
    quota: QuotaService = Depends(get_quota_service),
) -> ApiResponse[UploadDocumentData]:
    # 单库文档数 + 并发 PROCESSING 配额检查
    await quota.check_can_upload(ctx.tenant_id, req.kb_id, resolve_plan(ctx.plan))
    # 只建记录（写入原文 content）并投递异步任务，立即返回 PROCESSING。
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
    ctx: TenantContext = Depends(get_current_tenant),
    service: DocumentService = Depends(get_document_service),
    quota: QuotaService = Depends(get_quota_service),
) -> ApiResponse[DocumentStatusData]:
    # 并发 PROCESSING 配额检查（reindex 会新占一个索引名额）
    await quota.check_processing_capacity(ctx.tenant_id, resolve_plan(ctx.plan))
    data = await service.reindex(document_id, ctx.tenant_id)
    index_document_task.delay(document_id)
    return ApiResponse.success(data)
