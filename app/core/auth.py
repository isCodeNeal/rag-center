"""API Key 鉴权核心：Key 生成 / hash / 解析当前租户。

纯逻辑放这里（无 FastAPI 依赖），便于单测；FastAPI 依赖包装在 app/api/v1/deps.py。
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.exceptions import Unauthorized

# AUTH_ENABLED=false 时使用的内置默认租户
DEFAULT_TENANT_ID = "tenant_demo"
_KEY_PLAINTEXT_PREFIX = "rk_live_"


@dataclass
class TenantContext:
    """鉴权通过后的租户上下文。"""

    tenant_id: str
    tenant_name: str
    key_id: str
    key_prefix: str
    key_name: str
    # 套餐档位：free / standard / pro
    plan: str = "free"


def hash_api_key(plaintext: str) -> str:
    """对 Key 明文做 SHA-256，返回 64 位 hex。"""
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """生成一把新 Key。

    返回 (明文, key_hash, key_prefix)。明文格式 rk_live_<32位hex>；
    key_prefix = rk_ + 明文 hex 前 4 位（如 rk_a1b2）。明文只应打印一次，不落库。
    """
    hex_part = secrets.token_hex(16)  # 32 个 hex 字符
    plaintext = f"{_KEY_PLAINTEXT_PREFIX}{hex_part}"
    key_hash = hash_api_key(plaintext)
    key_prefix = f"rk_{hex_part[:4]}"
    return plaintext, key_hash, key_prefix


def _parse_bearer(authorization: str | None) -> str:
    if not authorization:
        raise Unauthorized(detail="missing Authorization header")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise Unauthorized(detail="malformed Authorization header")
    return parts[1].strip()


async def resolve_tenant(
    authorization: str | None,
    *,
    api_key_repo,
    tenant_repo,
    auth_enabled: bool,
) -> TenantContext:
    """从请求头解析当前租户。AUTH_ENABLED=false 时固定返回默认租户。"""
    if not auth_enabled:
        # AUTH_ENABLED=false 时固定使用内置默认租户，并按最高档 pro 执行 enforcement。
        return TenantContext(
            tenant_id=DEFAULT_TENANT_ID,
            tenant_name=DEFAULT_TENANT_ID,
            key_id="",
            key_prefix="",
            key_name="",
            plan="pro",
        )

    token = _parse_bearer(authorization)
    api_key = await api_key_repo.get_by_hash(hash_api_key(token))
    if api_key is None or api_key.status != "active":
        raise Unauthorized(detail="invalid or revoked api key")
    if api_key.expires_at is not None and api_key.expires_at < datetime.now(timezone.utc):
        raise Unauthorized(detail="api key expired")

    tenant = await tenant_repo.get(api_key.tenant_id)
    if tenant is None or tenant.status != "active":
        raise Unauthorized(detail="tenant not found or disabled")

    return TenantContext(
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        key_id=api_key.id,
        key_prefix=api_key.key_prefix,
        key_name=api_key.name,
        plan=getattr(tenant, "plan", None) or "free",
    )
