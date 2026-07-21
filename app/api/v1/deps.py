"""v1 版本级 FastAPI 依赖：当前租户解析。"""
from __future__ import annotations

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.auth import TenantContext, resolve_tenant
from app.core.config import settings
from app.repositories.api_key_repository import ApiKeyRepository
from app.repositories.tenant_repository import TenantRepository


async def get_current_tenant(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> TenantContext:
    return await resolve_tenant(
        authorization,
        api_key_repo=ApiKeyRepository(db),
        tenant_repo=TenantRepository(db),
        auth_enabled=settings.auth_enabled,
    )
