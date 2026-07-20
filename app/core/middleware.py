"""HTTP 请求 / 响应日志中间件。

为每个请求：
- 生成（或透传）request_id，注入 contextvar，并回写到响应头 X-Request-ID
- 记录 API_REQUEST：方法、URL、请求体（截断）
- 记录 API_RESPONSE：状态码、耗时、响应体（截断）

请求体在进入中间件时读取一次并被 Starlette 缓存，下游 handler 仍可正常解析。
"""
from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings
from app.core.logging import get_logger, new_request_id, set_request_id, truncate

logger = get_logger("app.access")

# 这些路径不记录，避免噪音。
_SKIP_PATHS = {"/health", "/docs", "/openapi.json", "/redoc", "/favicon.ico"}
_MAX_BODY = 1000


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 透传上游 request_id，没有则新建，便于全链路追踪。
        request_id = request.headers.get("X-Request-ID") or new_request_id()
        set_request_id(request_id)

        if request.url.path in _SKIP_PATHS:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response

        # 读取并缓存请求体（供日志 + 下游 handler 复用）。
        req_body = ""
        if settings.log_request_body:
            raw = await request.body()
            if raw:
                req_body = truncate(raw.decode("utf-8", "ignore"), _MAX_BODY)

        logger.info(
            "API_REQUEST | %s %s | body=%s",
            request.method,
            request.url.path,
            req_body or "-",
        )

        start = time.perf_counter()
        response = await call_next(request)
        cost_ms = (time.perf_counter() - start) * 1000

        # 读取响应体并重建响应（BaseHTTPMiddleware 的响应是流式的）。
        resp_body = b""
        async for chunk in response.body_iterator:
            resp_body += chunk

        body_preview = (
            truncate(resp_body.decode("utf-8", "ignore"), _MAX_BODY)
            if settings.log_request_body and resp_body
            else "-"
        )
        logger.info(
            "API_RESPONSE | %s %s | status=%s | cost=%.2fms | body=%s",
            request.method,
            request.url.path,
            response.status_code,
            cost_ms,
            body_preview,
        )

        new_response = Response(
            content=resp_body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )
        new_response.headers["X-Request-ID"] = request_id
        return new_response
