"""鉴权相关响应 schema。"""
from __future__ import annotations

from pydantic import BaseModel


class AuthMeData(BaseModel):
    tenant_id: str
    tenant_name: str
    key_prefix: str
    key_name: str
