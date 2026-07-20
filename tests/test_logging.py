"""日志工具的单元测试（不依赖文件时序）。"""
from __future__ import annotations

import pytest

from app.core.logging import (
    get_request_id,
    log_api,
    new_request_id,
    set_request_id,
    truncate,
)


def test_request_id_set_get():
    rid = new_request_id()
    set_request_id(rid)
    assert get_request_id() == rid
    assert len(rid) == 12


def test_truncate_long_text():
    out = truncate("a" * 1000, limit=100)
    assert out.startswith("a" * 100)
    assert "+900 chars" in out


def test_truncate_short_text():
    assert truncate("hello") == "hello"


async def test_log_api_async_decorator_returns_result():
    @log_api
    async def add(a, b):
        return a + b

    assert await add(2, 3) == 5


def test_log_api_sync_decorator_returns_result():
    @log_api
    def mul(a, b):
        return a * b

    assert mul(2, 3) == 6


async def test_log_api_propagates_exception():
    @log_api
    async def boom():
        raise ValueError("x")

    with pytest.raises(ValueError):
        await boom()
