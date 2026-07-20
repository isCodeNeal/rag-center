"""Unified API response envelope: {code, msg, data}."""
from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Standard response wrapper for all endpoints.

    code == 0 -> success; code != 0 -> failure (msg carries the reason, data may be null).
    """

    code: int = 0
    msg: str = "success"
    data: T | None = None

    @classmethod
    def success(cls, data: T | None = None, msg: str = "success") -> "ApiResponse[T]":
        return cls(code=0, msg=msg, data=data)

    @classmethod
    def error(cls, code: int, msg: str, data: T | None = None) -> "ApiResponse[T]":
        return cls(code=code, msg=msg, data=data)
