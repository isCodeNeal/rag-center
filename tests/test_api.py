"""基于依赖覆盖（dependency override）的 API 层测试（无需真实数据库 / embedding）。

验证成功、业务异常、请求校验异常三种场景下统一的 {code, msg, data} 响应外壳。
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_knowledge_base_service
from app.api.v1.deps import get_current_tenant
from app.core.auth import TenantContext
from app.core.exceptions import KnowledgeBaseNotFound
from app.main import app
from app.schemas.knowledge_base import (
    CreateKnowledgeBaseRequest,
    KnowledgeBaseData,
    KnowledgeTreeDoc,
    KnowledgeTreeKb,
    KnowledgeTreeTenant,
)

_FAKE_CTX = TenantContext(
    tenant_id="tenant_demo", tenant_name="演示租户",
    key_id="k1", key_prefix="rk_a1b2", key_name="本地开发",
)


class _FakeKBService:
    async def create(self, req: CreateKnowledgeBaseRequest, tenant_id: str) -> KnowledgeBaseData:
        return KnowledgeBaseData(
            kb_id="kb-test-123",
            name=req.name,
            tenant_id=tenant_id,
            created_at=datetime(2026, 6, 6, 10, 0, 0, tzinfo=timezone.utc),
        )


class _FailingKBService:
    async def create(self, req, tenant_id) -> KnowledgeBaseData:
        raise KnowledgeBaseNotFound("kb-missing")


@pytest.fixture
def client():
    return TestClient(app)


class _NoQuota:
    """放行所有配额检查，让 KB 接口测试聚焦响应外壳本身。"""

    async def check_can_create_kb(self, tenant_id, plan):
        return None


def _override_quota():
    from app.api.deps import get_quota_service

    app.dependency_overrides[get_quota_service] = lambda: _NoQuota()


def _clear_quota():
    from app.api.deps import get_quota_service

    app.dependency_overrides.pop(get_quota_service, None)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["code"] == 0


def test_create_kb_success(client):
    app.dependency_overrides[get_knowledge_base_service] = lambda: _FakeKBService()
    app.dependency_overrides[get_current_tenant] = lambda: _FAKE_CTX
    _override_quota()
    try:
        resp = client.post(
            "/api/v1/knowledge-bases/create",
            json={"name": "退款政策知识库", "description": "d"},
        )
    finally:
        app.dependency_overrides.pop(get_knowledge_base_service, None)
        app.dependency_overrides.pop(get_current_tenant, None)
        _clear_quota()

    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["msg"] == "success"
    assert body["data"]["kb_id"] == "kb-test-123"
    assert body["data"]["tenant_id"] == "tenant_demo"


def test_create_kb_validation_error(client):
    # 缺少必填的 `name` -> 返回带 PARAM_ERROR 码的统一响应外壳。
    # tenant_id 已从 schema 移除，仅发送 tenant_id 导致 name 缺失仍应触发 10001。
    app.dependency_overrides[get_current_tenant] = lambda: _FAKE_CTX
    try:
        resp = client.post(
            "/api/v1/knowledge-bases/create",
            json={"tenant_id": "tenant_demo"},
        )
    finally:
        app.dependency_overrides.pop(get_current_tenant, None)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 10001  # PARAM_ERROR
    assert body["data"] is None


def test_business_error_envelope(client):
    app.dependency_overrides[get_knowledge_base_service] = lambda: _FailingKBService()
    app.dependency_overrides[get_current_tenant] = lambda: _FAKE_CTX
    _override_quota()
    try:
        resp = client.post(
            "/api/v1/knowledge-bases/create",
            json={"name": "x"},
        )
    finally:
        app.dependency_overrides.pop(get_knowledge_base_service, None)
        app.dependency_overrides.pop(get_current_tenant, None)
        _clear_quota()

    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 10010  # KB_NOT_FOUND
    assert body["data"] is None


def test_request_id_header_present(client):
    resp = client.get("/health")
    assert resp.headers.get("X-Request-ID")


class _FakeTreeKBService:
    async def get_tree(self, tenant_id, keyword=None):
        doc = KnowledgeTreeDoc(
            document_id="doc-1",
            title="backend_engineer.md",
            status=1,
            chunk_count=12,
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        kb = KnowledgeTreeKb(
            kb_id="kb-1",
            name="技术岗位知识库",
            description="d",
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            documents=[doc],
        )
        return [KnowledgeTreeTenant(tenant_id="tech_position", knowledge_bases=[kb])]


def test_knowledge_tree_success(client):
    app.dependency_overrides[get_knowledge_base_service] = lambda: _FakeTreeKBService()
    app.dependency_overrides[get_current_tenant] = lambda: _FAKE_CTX
    try:
        resp = client.get("/api/v1/knowledge-bases/tree?keyword=tech")
    finally:
        app.dependency_overrides.pop(get_knowledge_base_service, None)
        app.dependency_overrides.pop(get_current_tenant, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"][0]["tenant_id"] == "tech_position"
    assert body["data"][0]["knowledge_bases"][0]["kb_id"] == "kb-1"
    assert body["data"][0]["knowledge_bases"][0]["documents"][0]["chunk_count"] == 12
