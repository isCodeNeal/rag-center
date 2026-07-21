"""鉴权校验接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.v1.deps import get_current_tenant
from app.core.auth import TenantContext
from app.schemas.auth import AuthMeData
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=ApiResponse[AuthMeData])
async def auth_me(ctx: TenantContext = Depends(get_current_tenant)) -> ApiResponse[AuthMeData]:
    data = AuthMeData(
        tenant_id=ctx.tenant_id,
        tenant_name=ctx.tenant_name,
        key_prefix=ctx.key_prefix,
        key_name=ctx.key_name,
    )
    return ApiResponse.success(data)
