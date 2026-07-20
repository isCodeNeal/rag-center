"""FastAPI 应用入口。

- 注册 v1 路由与请求日志中间件
- 注册全局异常处理器：把异常翻译成统一 {code, msg, data} 外壳（HTTP 200）
  - 业务异常 AppException -> 对应错误码 + 对外 msg；对内 detail 进日志
  - 请求校验异常          -> PARAM_ERROR(10001)
  - 未捕获异常            -> SERVER_ERROR(50000)，并记录完整堆栈
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestLoggingMiddleware

configure_logging()
logger = get_logger(__name__)

app = FastAPI(
    title="RAG Center",
    version="0.1.0",
    description="Unified RAG capability center — stage 1 skeleton.",
)

app.add_middleware(RequestLoggingMiddleware)


def _envelope(code: int, msg: str, data=None) -> JSONResponse:
    return JSONResponse(status_code=200, content={"code": code, "msg": msg, "data": data})


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    # 对内日志带完整上下文（错误码、路径、内部 detail）；对外只返回安全 msg。
    logger.warning(
        "BIZ_ERROR | code=%s | path=%s | msg=%s | detail=%s",
        exc.code,
        request.url.path,
        exc.msg,
        exc.detail,
    )
    return _envelope(exc.code, exc.msg, None)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    detail = "invalid request"
    if errors:
        first = errors[0]
        loc = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        detail = f"{loc} {first.get('msg', '')}".strip()
    logger.warning("PARAM_ERROR | path=%s | detail=%s", request.url.path, detail)
    return _envelope(ErrorCode.PARAM_ERROR.code, ErrorCode.PARAM_ERROR.msg, None)


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # 未预期异常：记录完整堆栈 + 异常类型 + 上下文，返回统一服务器错误。
    logger.exception(
        "SERVER_ERROR | path=%s | type=%s | error=%s",
        request.url.path,
        type(exc).__name__,
        exc,
    )
    return _envelope(ErrorCode.SERVER_ERROR.code, ErrorCode.SERVER_ERROR.msg, None)


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"code": 0, "msg": "success", "data": {"app": settings.app_name, "env": settings.app_env}}


app.include_router(api_router)
