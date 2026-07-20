"""models 和 schemas 之间共享的文档/检索状态枚举。"""
from __future__ import annotations

from enum import IntEnum


class DocumentStatus(IntEnum):
    """文档索引状态（存储在数据库中并通过 API 返回的整数枚举）。"""

    SUCCESS = 1
    FAILED = 2
    PROCESSING = 3  # 为未来的异步索引预留
