"""文档接口的 API 层测试（依赖覆盖，无需真实 DB / Redis / Celery）。

验证 upload 异步秒回 PROCESSING、状态查询、删除、reindex 的响应外壳与
Celery 任务投递（.delay 被 mock）。
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_document_service
from app.api.v1.deps import get_current_tenant
from app.core.auth import TenantContext
from app.core.exceptions import DocumentNotFound, raise_error
from app.core.error_codes import ErrorCode
from app.main import app
from app.models.document import Document
from app.models.enums import DocumentStatus
from app.schemas.document import DocumentStatusData

_FAKE_CTX = TenantContext(
    tenant_id="tenant_demo", tenant_name="演示租户",
    key_id="k1", key_prefix="rk_a1b2", key_name="本地开发",
)


def _doc(status: int) -> Document:
    d = Document(
        id="doc-1", tenant_id="tenant_demo", kb_id="kb-1",
        title="t", source_type="text", status=status, content="hello",
    )
    return d


class _FakeDocService:
    def __init__(self, *, status=DocumentStatus.PROCESSING.value):
        self._status = status
        self.reindexed = False

    async def create_document_record(self, req, tenant_id):
        return _doc(DocumentStatus.PROCESSING.value)

    async def get_status(self, document_id, tenant_id):
        if document_id != "doc-1":
            raise DocumentNotFound(document_id)
        return DocumentStatusData(
            document_id="doc-1", kb_id="kb-1", title="t",
            status=self._status, error_message=None, chunk_count=3,
            created_at=datetime(2026, 6, 6, tzinfo=timezone.utc),
            updated_at=datetime(2026, 6, 6, tzinfo=timezone.utc),
        )

    async def delete_document(self, document_id, tenant_id):
        if document_id != "doc-1":
            raise DocumentNotFound(document_id)
        return None

    async def reindex(self, document_id, tenant_id):
        self.reindexed = True
        return DocumentStatusData(
            document_id="doc-1", kb_id="kb-1", title="t",
            status=DocumentStatus.PROCESSING.value, error_message=None, chunk_count=0,
            created_at=datetime(2026, 6, 6, tzinfo=timezone.utc),
            updated_at=datetime(2026, 6, 6, tzinfo=timezone.utc),
        )


@pytest.fixture
def client(monkeypatch):
    # mock Celery .delay，避免连真实 broker
    import app.api.v1.routes.documents as doc_routes
    monkeypatch.setattr(doc_routes.index_document_task, "delay", lambda *a, **k: None)
    return TestClient(app)


class _NoQuota:
    async def check_can_upload(self, tenant_id, kb_id, plan):
        return None

    async def check_processing_capacity(self, tenant_id, plan):
        return None


def _override(svc):
    from app.api.deps import get_quota_service

    app.dependency_overrides[get_document_service] = lambda: svc
    app.dependency_overrides[get_current_tenant] = lambda: _FAKE_CTX
    app.dependency_overrides[get_quota_service] = lambda: _NoQuota()


def _clear():
    from app.api.deps import get_quota_service

    app.dependency_overrides.pop(get_document_service, None)
    app.dependency_overrides.pop(get_current_tenant, None)
    app.dependency_overrides.pop(get_quota_service, None)


def test_upload_returns_processing(client):
    _override(_FakeDocService())
    try:
        resp = client.post("/api/v1/documents/upload", json={
            "kb_id": "kb-1", "title": "t", "content": "hello world",
        })
    finally:
        _clear()
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["status"] == DocumentStatus.PROCESSING.value
    assert body["data"]["chunk_count"] == 0
    assert body["data"]["document_id"] == "doc-1"


def test_get_status_success(client):
    _override(_FakeDocService(status=DocumentStatus.SUCCESS.value))
    try:
        resp = client.get("/api/v1/documents/doc-1")
    finally:
        _clear()
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["status"] == DocumentStatus.SUCCESS.value
    assert body["data"]["chunk_count"] == 3


def test_get_status_not_found(client):
    _override(_FakeDocService())
    try:
        resp = client.get("/api/v1/documents/missing")
    finally:
        _clear()
    body = resp.json()
    assert body["code"] == ErrorCode.DOCUMENT_NOT_FOUND.code
    assert body["data"] is None


def test_delete_document(client):
    _override(_FakeDocService())
    try:
        resp = client.delete("/api/v1/documents/doc-1")
    finally:
        _clear()
    assert resp.json()["code"] == 0


def test_reindex_document(client):
    svc = _FakeDocService()
    _override(svc)
    try:
        resp = client.post("/api/v1/documents/doc-1/reindex")
    finally:
        _clear()
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["status"] == DocumentStatus.PROCESSING.value
    assert svc.reindexed is True
