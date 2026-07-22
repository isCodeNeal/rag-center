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
    KnowledgeBaseDetailData,
    KnowledgeTreeTenant,
    UpdateKnowledgeBaseRequest,
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


@router.get("/{kb_id}", response_model=ApiResponse[KnowledgeBaseDetailData])
async def get_knowledge_base(
    kb_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
    service: KnowledgeBaseService = Depends(get_knowledge_base_service),
) -> ApiResponse[KnowledgeBaseDetailData]:
    data = await service.get_detail(kb_id, ctx.tenant_id)
    return ApiResponse.success(data)


@router.patch("/{kb_id}", response_model=ApiResponse[KnowledgeBaseDetailData])
async def update_knowledge_base(
    kb_id: str,
    req: UpdateKnowledgeBaseRequest,
    ctx: TenantContext = Depends(get_current_tenant),
    service: KnowledgeBaseService = Depends(get_knowledge_base_service),
) -> ApiResponse[KnowledgeBaseDetailData]:
    data = await service.update(kb_id, ctx.tenant_id, req)
    return ApiResponse.success(data)


@router.delete("/{kb_id}", response_model=ApiResponse[None])
async def delete_knowledge_base(
    kb_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
    service: KnowledgeBaseService = Depends(get_knowledge_base_service),
) -> ApiResponse[None]:
    await service.delete(kb_id, ctx.tenant_id)
    return ApiResponse.success(None)
