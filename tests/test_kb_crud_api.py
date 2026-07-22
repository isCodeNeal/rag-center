"""知识库运维接口的 API 层测试（GET / PATCH / DELETE）。"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_knowledge_base_service
from app.api.v1.deps import get_current_tenant
from app.core.auth import TenantContext
from app.core.error_codes import ErrorCode
from app.core.exceptions import KnowledgeBaseNotFound, raise_error
from app.main import app
from app.schemas.knowledge_base import KnowledgeBaseDetailData

_FAKE_CTX = TenantContext(
    tenant_id="tenant_demo", tenant_name="演示租户",
    key_id="k1", key_prefix="rk_a1b2", key_name="本地开发",
)


def _detail(**over) -> KnowledgeBaseDetailData:
    base = dict(
        kb_id="kb-1", name="招聘制度库", description="d",
        settings={"synonyms": [{"terms": ["背调"], "expand": ["背景调查"]}]},
        document_count=2,
        created_at=datetime(2026, 6, 6, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 6, tzinfo=timezone.utc),
    )
    base.update(over)
    return KnowledgeBaseDetailData(**base)


class _FakeKBService:
    def __init__(self):
        self.deleted = False

    async def get_detail(self, kb_id, tenant_id):
        if kb_id != "kb-1":
            raise KnowledgeBaseNotFound(kb_id)
        return _detail()

    async def update(self, kb_id, tenant_id, req):
        if kb_id != "kb-1":
            raise KnowledgeBaseNotFound(kb_id)
        if req.settings is not None and not isinstance(req.settings.get("synonyms", []), list):
            raise_error(ErrorCode.PARAM_ERROR, msg="bad settings")
        return _detail(name=req.name or "招聘制度库")

    async def delete(self, kb_id, tenant_id):
        if kb_id != "kb-1":
            raise KnowledgeBaseNotFound(kb_id)
        self.deleted = True


@pytest.fixture
def client():
    return TestClient(app)


def _override(svc):
    app.dependency_overrides[get_knowledge_base_service] = lambda: svc
    app.dependency_overrides[get_current_tenant] = lambda: _FAKE_CTX


def _clear():
    app.dependency_overrides.pop(get_knowledge_base_service, None)
    app.dependency_overrides.pop(get_current_tenant, None)


def test_get_detail_success(client):
    _override(_FakeKBService())
    try:
        resp = client.get("/api/v1/knowledge-bases/kb-1")
    finally:
        _clear()
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["kb_id"] == "kb-1"
    assert body["data"]["document_count"] == 2
    assert body["data"]["settings"]["synonyms"][0]["terms"] == ["背调"]


def test_get_detail_not_found(client):
    _override(_FakeKBService())
    try:
        resp = client.get("/api/v1/knowledge-bases/missing")
    finally:
        _clear()
    assert resp.json()["code"] == ErrorCode.KB_NOT_FOUND.code


def test_patch_updates_name(client):
    _override(_FakeKBService())
    try:
        resp = client.patch("/api/v1/knowledge-bases/kb-1", json={"name": "新名字"})
    finally:
        _clear()
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["name"] == "新名字"


def test_delete_success(client):
    svc = _FakeKBService()
    _override(svc)
    try:
        resp = client.delete("/api/v1/knowledge-bases/kb-1")
    finally:
        _clear()
    assert resp.json()["code"] == 0
    assert svc.deleted is True
