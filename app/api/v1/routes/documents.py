"""上传文档接口（同步索引）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_document_service
from app.api.v1.deps import get_current_tenant
from app.core.auth import TenantContext
from app.schemas.common import ApiResponse
from app.schemas.document import UploadDocumentData, UploadDocumentRequest
from app.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=ApiResponse[UploadDocumentData])
async def upload_document(
    req: UploadDocumentRequest,
    ctx: TenantContext = Depends(get_current_tenant),
    service: DocumentService = Depends(get_document_service),
) -> ApiResponse[UploadDocumentData]:
    data = await service.upload(req, ctx.tenant_id)
    return ApiResponse.success(data)
