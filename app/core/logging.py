"""生产级日志工具。

能力概览：
- 统一格式：时间 | 级别 | 模块:函数:行号 | request_id | 内容
- 控制台彩色输出 + 文件按大小滚动（RotatingFileHandler）
- 两个文件：logs/app.log（全量）与 logs/error.log（仅 ERROR 及以上，方便快速排查）
- 非阻塞：QueueHandler + QueueListener，真正的磁盘/控制台写入在后台线程，业务线程只入队
- 异步安全：request_id 用 contextvars 存储，天然隔离每个请求/协程
- 低侵入：get_logger 全局可用；提供接口日志装饰器与 LLM 交互日志函数

日志格式示例：
2025-12-29 11:22:11 | INFO     | main:call_api:10 | - | API_REQUEST | call_api | args=() | kwargs={}
"""
from __future__ import annotations

import atexit
import functools
import logging
import os
import queue
import sys
import time
import uuid
from contextvars import ContextVar
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from typing import Any, Awaitable, Callable, TypeVar

from app.core.config import settings

# ---------------------------------------------------------------------------
# request_id：异步安全的请求追踪 ID（contextvar，默认 "-"）
# ---------------------------------------------------------------------------
_request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


def set_request_id(request_id: str) -> None:
    _request_id_var.set(request_id)


def get_request_id() -> str:
    return _request_id_var.get()


class _RequestIdFilter(logging.Filter):
    """把当前 contextvar 里的 request_id 注入每条日志记录。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_var.get()
        return True


# ---------------------------------------------------------------------------
# 格式与颜色
# ---------------------------------------------------------------------------
_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(module)s:%(funcName)s:%(lineno)d | %(request_id)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_LEVEL_COLORS = {
    logging.DEBUG: "\033[36m",     # 青
    logging.INFO: "\033[32m",      # 绿
    logging.WARNING: "\033[33m",   # 黄
    logging.ERROR: "\033[31m",     # 红
    logging.CRITICAL: "\033[1;31m",  # 加粗红
}
_RESET = "\033[0m"


class _ColorFormatter(logging.Formatter):
    """控制台彩色格式：仅给级别名着色，并保持 8 字符对齐。"""

    def format(self, record: logging.LogRecord) -> str:
        original = record.levelname
        color = _LEVEL_COLORS.get(record.levelno, "")
        if color:
            record.levelname = f"{color}{original:<8}{_RESET}"
            # 颜色格式里级别名已自带宽度，去掉 %(levelname)-8s 的固定宽度避免二次填充
            fmt = _LOG_FORMAT.replace("%(levelname)-8s", "%(levelname)s")
            self._style._fmt = fmt
        try:
            return super().format(record)
        finally:
            record.levelname = original


_configured = False
_listener: QueueListener | None = None


def configure_logging() -> None:
    """初始化全局日志（幂等）。app 启动时调用一次即可。"""
    global _configured, _listener
    if _configured:
        return

    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # 真正做输出的 handlers（运行在 QueueListener 后台线程里）。
    handlers: list[logging.Handler] = []

    # 1) 控制台彩色输出
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(_ColorFormatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    handlers.append(console)

    if settings.log_to_file:
        os.makedirs(settings.log_dir, exist_ok=True)
        plain = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

        # 2) 全量日志文件，按大小滚动
        app_file = RotatingFileHandler(
            os.path.join(settings.log_dir, "app.log"),
            maxBytes=settings.log_max_bytes,
            backupCount=settings.log_backup_count,
            encoding="utf-8",
        )
        app_file.setLevel(level)
        app_file.setFormatter(plain)
        handlers.append(app_file)

        # 3) 独立错误日志文件（仅 ERROR 及以上），方便快速排查线上问题
        error_file = RotatingFileHandler(
            os.path.join(settings.log_dir, "error.log"),
            maxBytes=settings.log_max_bytes,
            backupCount=settings.log_backup_count,
            encoding="utf-8",
        )
        error_file.setLevel(logging.ERROR)
        error_file.setFormatter(plain)
        handlers.append(error_file)

    # 非阻塞：业务线程只把日志塞进队列，后台线程负责写文件/控制台。
    log_queue: queue.Queue = queue.Queue(-1)
    queue_handler = QueueHandler(log_queue)
    # 在入队线程（即请求线程）里注入 request_id，保证 contextvar 上下文正确。
    queue_handler.addFilter(_RequestIdFilter())

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers[:] = [queue_handler]

    _listener = QueueListener(log_queue, *handlers, respect_handler_level=True)
    _listener.start()
    atexit.register(_shutdown)

    # 收敛第三方库噪音
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    _configured = True


def _shutdown() -> None:
    global _listener
    if _listener is not None:
        _listener.stop()
        _listener = None


def get_logger(name: str) -> logging.Logger:
    """全局获取 logger。首次调用会确保日志已初始化。"""
    configure_logging()
    return logging.getLogger(name)


# ---------------------------------------------------------------------------
# 工具：截断，避免超长 prompt / body 撑爆日志
# ---------------------------------------------------------------------------
def truncate(value: Any, limit: int = 500) -> str:
    text = value if isinstance(value, str) else repr(value)
    if len(text) > limit:
        return f"{text[:limit]}...(+{len(text) - limit} chars)"
    return text


# ---------------------------------------------------------------------------
# 接口 / 函数调用日志装饰器（同步 + 异步通用）
# ---------------------------------------------------------------------------
F = TypeVar("F", bound=Callable[..., Any])
_api_logger = logging.getLogger("app.api")


def log_api(func: F) -> F:
    """记录函数调用的入参、返回与耗时，输出 API_REQUEST / API_RESPONSE。

    用法::

        @log_api
        async def call_api(...): ...
    """
    name = func.__name__

    if _is_coroutine(func):

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            configure_logging()
            _api_logger.info("API_REQUEST | %s | args=%s | kwargs=%s", name, args, truncate(kwargs))
            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                cost = (time.perf_counter() - start) * 1000
                _api_logger.exception("API_ERROR | %s | cost=%.2fms | error=%s", name, cost, exc)
                raise
            cost = (time.perf_counter() - start) * 1000
            _api_logger.info("API_RESPONSE | %s | cost=%.2fms | result=%s", name, cost, truncate(result))
            return result

        return async_wrapper  # type: ignore[return-value]

    @functools.wraps(func)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        configure_logging()
        _api_logger.info("API_REQUEST | %s | args=%s | kwargs=%s", name, args, truncate(kwargs))
        start = time.perf_counter()
        try:
            result = func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            cost = (time.perf_counter() - start) * 1000
            _api_logger.exception("API_ERROR | %s | cost=%.2fms | error=%s", name, cost, exc)
            raise
        cost = (time.perf_counter() - start) * 1000
        _api_logger.info("API_RESPONSE | %s | cost=%.2fms | result=%s", name, cost, truncate(result))
        return result

    return sync_wrapper  # type: ignore[return-value]


def _is_coroutine(func: Callable[..., Any]) -> bool:
    import inspect

    return inspect.iscoroutinefunction(func)


# ---------------------------------------------------------------------------
# 大模型交互专用日志
# ---------------------------------------------------------------------------
_llm_logger = logging.getLogger("app.llm")


def log_llm_request(model: str, prompt: Any, **extra: Any) -> None:
    """记录一次大模型 / embedding 调用的输入。"""
    configure_logging()
    suffix = _fmt_extra(extra)
    _llm_logger.info("LLM_REQUEST | model=%s | prompt=%s%s", model, truncate(prompt), suffix)


def log_llm_response(model: str, response: Any, *, cost_ms: float | None = None, **extra: Any) -> None:
    """记录一次大模型 / embedding 调用的返回与耗时。"""
    configure_logging()
    cost = f" | cost={cost_ms:.2f}ms" if cost_ms is not None else ""
    suffix = _fmt_extra(extra)
    _llm_logger.info("LLM_RESPONSE | model=%s%s | response=%s%s", model, cost, truncate(response), suffix)


def log_llm_error(model: str, error: Any, *, cost_ms: float | None = None, **extra: Any) -> None:
    """记录一次大模型 / embedding 调用的异常。"""
    configure_logging()
    cost = f" | cost={cost_ms:.2f}ms" if cost_ms is not None else ""
    suffix = _fmt_extra(extra)
    _llm_logger.error("LLM_ERROR | model=%s%s | error=%s%s", model, cost, truncate(error), suffix)


def _fmt_extra(extra: dict[str, Any]) -> str:
    if not extra:
        return ""
    return " | " + " | ".join(f"{k}={truncate(v, 120)}" for k, v in extra.items())
