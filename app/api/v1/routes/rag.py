"""RAG 检索增强接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_rag_service
from app.schemas.common import ApiResponse
from app.schemas.rag import RetrieveData, RetrieveRequest
from app.services.rag_service import RAGService

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/retrieve", response_model=ApiResponse[RetrieveData])
async def retrieve(
    req: RetrieveRequest,
    service: RAGService = Depends(get_rag_service),
) -> ApiResponse[RetrieveData]:
    data = await service.retrieve(req)
    return ApiResponse.success(data)
