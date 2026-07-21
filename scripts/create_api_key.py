"""给已有租户发 Key：python scripts/create_api_key.py --tenant-id tenant_demo --name "本地开发"。

明文只在此处打印一次，库里只存 hash。
"""
from __future__ import annotations

import argparse
import asyncio

from app.core.auth import generate_api_key
from app.db.session import SessionLocal
from app.models.api_key import ApiKey
from app.repositories.api_key_repository import ApiKeyRepository
from app.repositories.tenant_repository import TenantRepository


async def _main(tenant_id: str, name: str) -> None:
    plaintext, key_hash, key_prefix = generate_api_key()
    async with SessionLocal() as session:
        if await TenantRepository(session).get(tenant_id) is None:
            raise SystemExit(f"租户不存在：{tenant_id}")
        await ApiKeyRepository(session).create(
            ApiKey(
                tenant_id=tenant_id,
                key_hash=key_hash,
                key_prefix=key_prefix,
                name=name,
                status="active",
            )
        )
        await session.commit()
    print("API Key 创建成功（明文只显示这一次，请立即保存）：")
    print(f"  tenant_id : {tenant_id}")
    print(f"  key_prefix: {key_prefix}")
    print(f"  api_key   : {plaintext}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="给租户发 API Key")
    parser.add_argument("--tenant-id", required=True, help="已有租户 id")
    parser.add_argument("--name", required=True, help="Key 备注，如 客服系统对接")
    args = parser.parse_args()
    asyncio.run(_main(args.tenant_id, args.name))
