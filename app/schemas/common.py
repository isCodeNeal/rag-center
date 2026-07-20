"""统一的 API 响应封装：{code, msg, data}。"""
from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """所有接口的标准响应包装类。

    code == 0 表示成功；code != 0 表示失败（msg 携带失败原因，data 可能为 null）。
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
