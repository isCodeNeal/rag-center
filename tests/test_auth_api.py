"""/auth/me 与鉴权信封测试。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.v1.deps import get_current_tenant
from app.core.auth import TenantContext
from app.core.exceptions import Unauthorized
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_auth_me_success(client):
    ctx = TenantContext(
        tenant_id="tenant_demo", tenant_name="演示租户",
        key_id="k1", key_prefix="rk_a1b2", key_name="本地开发",
        plan="standard",
    )

    class _FakeQuota:
        async def get_kb_count(self, tenant_id):
            return 3

    class _FakeRateLimit:
        async def get_daily_count(self, tenant_id):
            return 128

    from app.api.deps import get_quota_service, get_rate_limit_service

    app.dependency_overrides[get_current_tenant] = lambda: ctx
    app.dependency_overrides[get_quota_service] = lambda: _FakeQuota()
    app.dependency_overrides[get_rate_limit_service] = lambda: _FakeRateLimit()
    try:
        resp = client.get("/api/v1/auth/me")
    finally:
        app.dependency_overrides.pop(get_current_tenant, None)
        app.dependency_overrides.pop(get_quota_service, None)
        app.dependency_overrides.pop(get_rate_limit_service, None)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    d = body["data"]
    assert d["tenant_id"] == "tenant_demo"
    assert d["plan"] == "standard"
    assert d["features"]["hybrid_allowed"] is True
    assert d["features"]["rerank_allowed"] is False
    assert d["features"]["allowed_profiles"] == ["speed", "balanced", "custom"]
    assert d["limits"]["max_kb"] == 5
    assert d["usage"] == {"kb_count": 3, "retrieve_daily_count": 128}


def test_auth_me_unauthorized_envelope(client):
    def _raise():
        raise Unauthorized(detail="no key")

    app.dependency_overrides[get_current_tenant] = _raise
    try:
        resp = client.get("/api/v1/auth/me")
    finally:
        app.dependency_overrides.pop(get_current_tenant, None)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 20010
    assert body["data"] is None
