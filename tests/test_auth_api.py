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
    )
    app.dependency_overrides[get_current_tenant] = lambda: ctx
    try:
        resp = client.get("/api/v1/auth/me")
    finally:
        app.dependency_overrides.pop(get_current_tenant, None)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"] == {
        "tenant_id": "tenant_demo",
        "tenant_name": "演示租户",
        "key_prefix": "rk_a1b2",
        "key_name": "本地开发",
    }


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
