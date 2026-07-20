"""Upload document endpoint (synchronous indexing)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_document_service
from app.schemas.common import ApiResponse
from app.schemas.document import UploadDocumentData, UploadDocumentRequest
from app.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=ApiResponse[UploadDocumentData])
async def upload_document(
    req: UploadDocumentRequest,
    service: DocumentService = Depends(get_document_service),
) -> ApiResponse[UploadDocumentData]:
    data = await service.upload(req)
    return ApiResponse.success(data)
