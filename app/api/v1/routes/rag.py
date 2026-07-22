"""RAG 检索增强接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_feedback_service, get_rag_service
from app.api.v1.deps import get_current_tenant
from app.core.auth import TenantContext
from app.schemas.common import ApiResponse
from app.schemas.feedback import FeedbackData, FeedbackRequest
from app.schemas.rag import RetrieveData, RetrieveRequest
from app.services.feedback_service import FeedbackService
from app.services.rag_service import RAGService

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/retrieve", response_model=ApiResponse[RetrieveData])
async def retrieve(
    req: RetrieveRequest,
    ctx: TenantContext = Depends(get_current_tenant),
    service: RAGService = Depends(get_rag_service),
) -> ApiResponse[RetrieveData]:
    data = await service.retrieve(req, ctx.tenant_id, ctx.plan)
    return ApiResponse.success(data)


@router.post("/feedback", response_model=ApiResponse[FeedbackData])
async def submit_feedback(
    req: FeedbackRequest,
    ctx: TenantContext = Depends(get_current_tenant),
    service: FeedbackService = Depends(get_feedback_service),
) -> ApiResponse[FeedbackData]:
    data = await service.submit(req, ctx.tenant_id)
    return ApiResponse.success(data)
