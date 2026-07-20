"""Create knowledge base endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_knowledge_base_service
from app.schemas.common import ApiResponse
from app.schemas.knowledge_base import CreateKnowledgeBaseRequest, KnowledgeBaseData
from app.services.knowledge_base_service import KnowledgeBaseService

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])


@router.post("/create", response_model=ApiResponse[KnowledgeBaseData])
async def create_knowledge_base(
    req: CreateKnowledgeBaseRequest,
    service: KnowledgeBaseService = Depends(get_knowledge_base_service),
) -> ApiResponse[KnowledgeBaseData]:
    data = await service.create(req)
    return ApiResponse.success(data)
