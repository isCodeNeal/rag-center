"""反馈 API 测试：正常提交、log_id 不匹配、Langfuse 关闭时的错误码。"""
from __future__ import annotations

import pytest

from app.core.error_codes import ErrorCode
from app.core.exceptions import FeedbackFailed, FeedbackInvalid


# --- error codes ---

def test_feedback_error_codes():
    assert ErrorCode.FEEDBACK_FAILED.code == 20020
    assert ErrorCode.FEEDBACK_INVALID.code == 20021
    assert ErrorCode.SCORE_OUT_OF_RANGE.code == 20022


def test_feedback_invalid_exception():
    exc = FeedbackInvalid(detail="mismatch")
    assert exc.code == 20021


def test_feedback_failed_exception():
    exc = FeedbackFailed(detail="langfuse down")
    assert exc.code == 20020


# --- FeedbackService unit tests ---

class _FakeLogRepo:
    def __init__(self, log=None):
        self._log = log

    async def get(self, log_id):
        return self._log


class _FakeLog:
    def __init__(self, tenant_id, trace_id):
        self.tenant_id = tenant_id
        self.trace_id = trace_id


class _FakeSession:
    async def commit(self):
        pass


@pytest.mark.asyncio
async def test_feedback_langfuse_disabled_raises_failed():
    from app.services.feedback_service import FeedbackService
    from app.schemas.feedback import FeedbackRequest
    import unittest.mock as mock

    svc = FeedbackService(_FakeSession(), retrieval_log_repository=_FakeLogRepo())
    req = FeedbackRequest(trace_id="trace-1", score=4)

    with mock.patch("app.services.feedback_service.get_langfuse_client", return_value=None):
        with pytest.raises(FeedbackFailed):
            await svc.submit(req, "tenant_demo")


@pytest.mark.asyncio
async def test_feedback_log_id_tenant_mismatch_raises_invalid():
    from app.services.feedback_service import FeedbackService
    from app.schemas.feedback import FeedbackRequest
    import unittest.mock as mock

    wrong_log = _FakeLog(tenant_id="other_tenant", trace_id="trace-1")
    svc = FeedbackService(_FakeSession(), retrieval_log_repository=_FakeLogRepo(wrong_log))
    req = FeedbackRequest(trace_id="trace-1", log_id="log-1", score=4)

    with mock.patch("app.services.feedback_service.get_langfuse_client", return_value=None):
        with pytest.raises(FeedbackInvalid):
            await svc.submit(req, "tenant_demo")


@pytest.mark.asyncio
async def test_feedback_trace_id_mismatch_raises_invalid():
    from app.services.feedback_service import FeedbackService
    from app.schemas.feedback import FeedbackRequest
    import unittest.mock as mock

    log = _FakeLog(tenant_id="tenant_demo", trace_id="trace-DIFFERENT")
    svc = FeedbackService(_FakeSession(), retrieval_log_repository=_FakeLogRepo(log))
    req = FeedbackRequest(trace_id="trace-1", log_id="log-1", score=4)

    with mock.patch("app.services.feedback_service.get_langfuse_client", return_value=None):
        with pytest.raises(FeedbackInvalid):
            await svc.submit(req, "tenant_demo")


@pytest.mark.asyncio
async def test_feedback_schema_score_validation():
    from app.schemas.feedback import FeedbackRequest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        FeedbackRequest(trace_id="t1", score=0)

    with pytest.raises(ValidationError):
        FeedbackRequest(trace_id="t1", score=6)

    req = FeedbackRequest(trace_id="t1", score=5)
    assert req.score == 5
