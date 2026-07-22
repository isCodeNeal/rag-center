"""鉴权校验接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_quota_service, get_rate_limit_service
from app.api.v1.deps import get_current_tenant
from app.core.auth import TenantContext
from app.schemas.auth import (
    AuthMeData,
    AuthMeFeatures,
    AuthMeLimits,
    AuthMeUsage,
)
from app.schemas.common import ApiResponse
from app.services.quota_service import QuotaService
from app.services.rate_limit_service import RateLimitService
from app.tenant.plan_resolver import resolve_plan

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=ApiResponse[AuthMeData])
async def auth_me(
    ctx: TenantContext = Depends(get_current_tenant),
    quota: QuotaService = Depends(get_quota_service),
    rate_limit: RateLimitService = Depends(get_rate_limit_service),
) -> ApiResponse[AuthMeData]:
    plan = resolve_plan(ctx.plan)
    kb_count = await quota.get_kb_count(ctx.tenant_id)
    daily_count = await rate_limit.get_daily_count(ctx.tenant_id)
    data = AuthMeData(
        tenant_id=ctx.tenant_id,
        tenant_name=ctx.tenant_name,
        key_prefix=ctx.key_prefix,
        key_name=ctx.key_name,
        plan=plan.plan,
        features=AuthMeFeatures(
            allowed_profiles=plan.features.allowed_profiles,
            hybrid_allowed=plan.features.hybrid_allowed,
            rerank_allowed=plan.features.rerank_allowed,
            query_rewrite_allowed=plan.features.query_rewrite_allowed,
        ),
        limits=AuthMeLimits(
            retrieve_qps=plan.limits.retrieve_qps,
            retrieve_daily=plan.limits.retrieve_daily,
            max_kb=plan.limits.max_kb,
            max_documents_per_kb=plan.limits.max_documents_per_kb,
            max_processing_documents=plan.limits.max_processing_documents,
        ),
        usage=AuthMeUsage(kb_count=kb_count, retrieve_daily_count=daily_count),
    )
    return ApiResponse.success(data)
