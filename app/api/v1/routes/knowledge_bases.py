"""知识库接口：创建、树形查询。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_knowledge_base_service
from app.api.v1.deps import get_current_tenant
from app.core.auth import TenantContext
from app.schemas.common import ApiResponse
from app.schemas.knowledge_base import (
    CreateKnowledgeBaseRequest,
    KnowledgeBaseData,
    KnowledgeTreeTenant,
)
from app.services.knowledge_base_service import KnowledgeBaseService

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])


@router.post("/create", response_model=ApiResponse[KnowledgeBaseData])
async def create_knowledge_base(
    req: CreateKnowledgeBaseRequest,
    ctx: TenantContext = Depends(get_current_tenant),
    service: KnowledgeBaseService = Depends(get_knowledge_base_service),
) -> ApiResponse[KnowledgeBaseData]:
    data = await service.create(req, ctx.tenant_id)
    return ApiResponse.success(data)


@router.get("/tree", response_model=ApiResponse[list[KnowledgeTreeTenant]])
async def get_knowledge_tree(
    keyword: str | None = None,
    ctx: TenantContext = Depends(get_current_tenant),
    service: KnowledgeBaseService = Depends(get_knowledge_base_service),
) -> ApiResponse[list[KnowledgeTreeTenant]]:
    data = await service.get_tree(ctx.tenant_id, keyword)
    return ApiResponse.success(data)
