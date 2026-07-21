"""API Key 鉴权单元测试。"""
from __future__ import annotations

from app.core.error_codes import ErrorCode
from app.core.exceptions import Unauthorized


def test_api_key_invalid_error_code_is_20010():
    assert ErrorCode.API_KEY_INVALID.code == 20010


def test_unauthorized_exception_uses_20010():
    exc = Unauthorized(detail="no key")
    assert exc.code == 20010
    assert exc.detail == "no key"


import pytest
from datetime import datetime, timedelta, timezone

from app.core.auth import (
    DEFAULT_TENANT_ID,
    TenantContext,
    generate_api_key,
    hash_api_key,
    resolve_tenant,
)


def test_generate_api_key_format():
    plaintext, key_hash, key_prefix = generate_api_key()
    assert plaintext.startswith("rk_live_")
    assert len(plaintext) == len("rk_live_") + 32
    assert key_hash == hash_api_key(plaintext)
    assert len(key_hash) == 64
    assert key_prefix.startswith("rk_") and len(key_prefix) == 7


class _FakeTenant:
    def __init__(self, id="tenant_demo", name="演示租户", status="active"):
        self.id, self.name, self.status = id, name, status


class _FakeApiKey:
    def __init__(self, *, tenant_id="tenant_demo", status="active", expires_at=None,
                 id="key-1", key_prefix="rk_a1b2", name="本地开发", key_hash="h"):
        self.tenant_id, self.status, self.expires_at = tenant_id, status, expires_at
        self.id, self.key_prefix, self.name, self.key_hash = id, key_prefix, name, key_hash


class _FakeApiKeyRepo:
    def __init__(self, api_key=None):
        self._api_key = api_key

    async def get_by_hash(self, key_hash):
        return self._api_key


class _FakeTenantRepo:
    def __init__(self, tenant=None):
        self._tenant = tenant

    async def get(self, tenant_id):
        return self._tenant


@pytest.mark.asyncio
async def test_resolve_tenant_disabled_returns_default():
    ctx = await resolve_tenant(
        None, api_key_repo=_FakeApiKeyRepo(), tenant_repo=_FakeTenantRepo(), auth_enabled=False
    )
    assert ctx.tenant_id == DEFAULT_TENANT_ID


@pytest.mark.asyncio
async def test_resolve_tenant_valid_key_returns_context():
    ctx = await resolve_tenant(
        "Bearer rk_live_abc",
        api_key_repo=_FakeApiKeyRepo(_FakeApiKey()),
        tenant_repo=_FakeTenantRepo(_FakeTenant()),
        auth_enabled=True,
    )
    assert ctx.tenant_id == "tenant_demo"
    assert ctx.tenant_name == "演示租户"
    assert ctx.key_prefix == "rk_a1b2"
    assert ctx.key_name == "本地开发"


@pytest.mark.asyncio
async def test_resolve_tenant_missing_header_raises():
    with pytest.raises(Unauthorized):
        await resolve_tenant(None, api_key_repo=_FakeApiKeyRepo(), tenant_repo=_FakeTenantRepo(), auth_enabled=True)


@pytest.mark.asyncio
async def test_resolve_tenant_unknown_key_raises():
    with pytest.raises(Unauthorized):
        await resolve_tenant("Bearer rk_live_x", api_key_repo=_FakeApiKeyRepo(None),
                             tenant_repo=_FakeTenantRepo(), auth_enabled=True)


@pytest.mark.asyncio
async def test_resolve_tenant_revoked_key_raises():
    with pytest.raises(Unauthorized):
        await resolve_tenant("Bearer rk_live_x", api_key_repo=_FakeApiKeyRepo(_FakeApiKey(status="revoked")),
                             tenant_repo=_FakeTenantRepo(_FakeTenant()), auth_enabled=True)


@pytest.mark.asyncio
async def test_resolve_tenant_expired_key_raises():
    past = datetime.now(timezone.utc) - timedelta(days=1)
    with pytest.raises(Unauthorized):
        await resolve_tenant("Bearer rk_live_x", api_key_repo=_FakeApiKeyRepo(_FakeApiKey(expires_at=past)),
                             tenant_repo=_FakeTenantRepo(_FakeTenant()), auth_enabled=True)


@pytest.mark.asyncio
async def test_resolve_tenant_disabled_tenant_raises():
    with pytest.raises(Unauthorized):
        await resolve_tenant("Bearer rk_live_x", api_key_repo=_FakeApiKeyRepo(_FakeApiKey()),
                             tenant_repo=_FakeTenantRepo(_FakeTenant(status="disabled")), auth_enabled=True)
