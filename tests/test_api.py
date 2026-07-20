"""基于依赖覆盖（dependency override）的 API 层测试（无需真实数据库 / embedding）。

验证成功、业务异常、请求校验异常三种场景下统一的 {code, msg, data} 响应外壳。
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_knowledge_base_service
from app.core.exceptions import KnowledgeBaseNotFound
from app.main import app
from app.schemas.knowledge_base import CreateKnowledgeBaseRequest, KnowledgeBaseData


class _FakeKBService:
    async def create(self, req: CreateKnowledgeBaseRequest) -> KnowledgeBaseData:
        return KnowledgeBaseData(
            kb_id="kb-test-123",
            name=req.name,
            tenant_id=req.tenant_id,
            created_at=datetime(2026, 6, 6, 10, 0, 0, tzinfo=timezone.utc),
        )


class _FailingKBService:
    async def create(self, req: CreateKnowledgeBaseRequest) -> KnowledgeBaseData:
        raise KnowledgeBaseNotFound("kb-missing")


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["code"] == 0


def test_create_kb_success(client):
    app.dependency_overrides[get_knowledge_base_service] = lambda: _FakeKBService()
    try:
        resp = client.post(
            "/api/v1/knowledge-bases/create",
            json={"name": "退款政策知识库", "description": "d", "tenant_id": "tenant_demo"},
        )
    finally:
        app.dependency_overrides.pop(get_knowledge_base_service, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["msg"] == "success"
    assert body["data"]["kb_id"] == "kb-test-123"
    assert body["data"]["tenant_id"] == "tenant_demo"


def test_create_kb_validation_error(client):
    # 缺少必填的 `name` -> 返回带 PARAM_ERROR 码的统一响应外壳。
    resp = client.post(
        "/api/v1/knowledge-bases/create",
        json={"tenant_id": "tenant_demo"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 10001  # PARAM_ERROR
    assert body["data"] is None


def test_business_error_envelope(client):
    app.dependency_overrides[get_knowledge_base_service] = lambda: _FailingKBService()
    try:
        resp = client.post(
            "/api/v1/knowledge-bases/create",
            json={"name": "x", "tenant_id": "tenant_demo"},
        )
    finally:
        app.dependency_overrides.pop(get_knowledge_base_service, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 10010  # KB_NOT_FOUND
    assert body["data"] is None


def test_request_id_header_present(client):
    resp = client.get("/health")
    assert resp.headers.get("X-Request-ID")
