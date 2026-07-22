"""套餐 / 配额 / 限流：plan_resolver、retrieve profile 校验、quota、rate_limit。"""
from __future__ import annotations

import pytest

from app.core.exceptions import FeatureNotAllowed, QuotaExceeded, RetrieveRateLimited
from app.schemas.rag import RetrieveRequest
from app.tenant.plan_resolver import resolve_plan
from app.tenant.retrieve_presets import DEFAULT_PROFILE


# ---- plan_resolver ----

def test_resolve_plan_three_tiers():
    assert resolve_plan("free").features.allowed_profiles == ["speed"]
    assert resolve_plan("standard").features.hybrid_allowed is True
    assert resolve_plan("standard").features.rerank_allowed is False
    pro = resolve_plan("pro")
    assert pro.features.rerank_allowed is True
    assert pro.features.query_rewrite_allowed is True
    assert "quality" in pro.features.allowed_profiles


def test_resolve_plan_unknown_falls_back_to_free():
    assert resolve_plan("garbage").plan == "free"
    assert resolve_plan(None).plan == "free"


# ---- retrieve profile 校验（直接测 RAGService._resolve_profile_and_options）----

def _make_service():
    from app.services.rag_service import RAGService

    return RAGService(
        None,
        kb_repository=None,
        retrieval_log_repository=None,
        embedding_provider=None,
        vector_store=None,
        vector_store_name="pgvector",
        keyword_search_provider=None,
        keyword_search_provider_name=None,
        rerank_provider=None,
        hybrid_search_service=None,
        query_pipeline=None,
    )


def test_free_speed_ok():
    svc = _make_service()
    req = RetrieveRequest(kb_id="k", user_id="u", query="q", profile="speed")
    profile, mode, top_k, rerank, rewrite = svc._resolve_profile_and_options(
        req, resolve_plan("free")
    )
    assert profile == "speed"
    assert mode == "vector"
    assert top_k == 3
    assert rerank is False and rewrite is False


def test_free_balanced_rejected():
    svc = _make_service()
    req = RetrieveRequest(kb_id="k", user_id="u", query="q", profile="balanced")
    with pytest.raises(FeatureNotAllowed):
        svc._resolve_profile_and_options(req, resolve_plan("free"))


def test_default_profile_is_balanced():
    svc = _make_service()
    req = RetrieveRequest(kb_id="k", user_id="u", query="q")  # 不传 profile
    profile, mode, *_ = svc._resolve_profile_and_options(req, resolve_plan("standard"))
    assert profile == DEFAULT_PROFILE == "balanced"
    assert mode == "hybrid"


def test_pro_quality_expands_rerank_and_rewrite():
    svc = _make_service()
    req = RetrieveRequest(kb_id="k", user_id="u", query="q", profile="quality")
    profile, mode, top_k, rerank, rewrite = svc._resolve_profile_and_options(
        req, resolve_plan("pro")
    )
    assert profile == "quality"
    assert mode == "hybrid" and top_k == 8
    assert rerank is True and rewrite is True


def test_standard_custom_with_rerank_rejected():
    svc = _make_service()
    req = RetrieveRequest(
        kb_id="k", user_id="u", query="q", profile="custom",
        rerank_options={"enabled": True},
    )
    with pytest.raises(FeatureNotAllowed):
        svc._resolve_profile_and_options(req, resolve_plan("standard"))


def test_standard_custom_vector_ok():
    svc = _make_service()
    req = RetrieveRequest(
        kb_id="k", user_id="u", query="q", profile="custom",
        retrieval_options={"mode": "vector"},
        rerank_options={"enabled": False},
    )
    profile, mode, top_k, rerank, rewrite = svc._resolve_profile_and_options(
        req, resolve_plan("standard")
    )
    assert profile == "custom" and mode == "vector" and rerank is False


# ---- QuotaService ----

class _FakeKBRepo:
    def __init__(self, count):
        self._count = count

    async def count_by_tenant(self, tenant_id):
        return self._count


class _FakeDocRepo:
    def __init__(self, kb_count=0, processing=0):
        self._kb_count = kb_count
        self._processing = processing

    async def count_by_kb(self, kb_id):
        return self._kb_count

    async def count_processing_by_tenant(self, tenant_id):
        return self._processing


@pytest.mark.asyncio
async def test_quota_kb_limit_blocks_second_free_kb():
    from app.services.quota_service import QuotaService

    svc = QuotaService(kb_repository=_FakeKBRepo(1), document_repository=_FakeDocRepo())
    with pytest.raises(QuotaExceeded):
        await svc.check_can_create_kb("t1", resolve_plan("free"))


@pytest.mark.asyncio
async def test_quota_kb_ok_under_limit():
    from app.services.quota_service import QuotaService

    svc = QuotaService(kb_repository=_FakeKBRepo(0), document_repository=_FakeDocRepo())
    await svc.check_can_create_kb("t1", resolve_plan("free"))  # 不抛


@pytest.mark.asyncio
async def test_quota_processing_capacity_blocks():
    from app.services.quota_service import QuotaService

    svc = QuotaService(
        kb_repository=_FakeKBRepo(0),
        document_repository=_FakeDocRepo(kb_count=0, processing=1),
    )
    with pytest.raises(QuotaExceeded):
        await svc.check_processing_capacity("t1", resolve_plan("free"))


# ---- RateLimitService ----

class _FakeRedis:
    def __init__(self, initial=None):
        self.store = dict(initial or {})

    async def get(self, key):
        v = self.store.get(key)
        return None if v is None else str(v)

    async def incr(self, key):
        self.store[key] = int(self.store.get(key, 0)) + 1
        return self.store[key]

    async def expire(self, key, ttl):
        return True


@pytest.mark.asyncio
async def test_rate_limit_qps_exceeded():
    from app.services.rate_limit_service import RateLimitService

    redis = _FakeRedis()
    svc = RateLimitService(redis)
    plan = resolve_plan("free")  # qps=3
    # 前 3 次 OK，第 4 次超限
    for _ in range(3):
        await svc.check_retrieve("t1", plan)
    with pytest.raises(RetrieveRateLimited):
        await svc.check_retrieve("t1", plan)


@pytest.mark.asyncio
async def test_rate_limit_daily_exceeded():
    from app.services.rate_limit_service import RateLimitService
    import time

    day = time.strftime("%Y%m%d", time.gmtime())
    redis = _FakeRedis({f"rag:quota:retrieve:daily:t1:{day}": 500})  # free daily=500
    svc = RateLimitService(redis)
    with pytest.raises(QuotaExceeded):
        await svc.check_retrieve("t1", resolve_plan("free"))


@pytest.mark.asyncio
async def test_rate_limit_record_and_get_daily():
    from app.services.rate_limit_service import RateLimitService

    redis = _FakeRedis()
    svc = RateLimitService(redis)
    await svc.record_retrieve_success("t1")
    await svc.record_retrieve_success("t1")
    assert await svc.get_daily_count("t1") == 2
