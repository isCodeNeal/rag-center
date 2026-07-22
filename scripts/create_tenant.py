"""注册租户：python scripts/create_tenant.py --id tenant_demo --name "演示租户"。"""
from __future__ import annotations

import argparse
import asyncio

from app.db.session import SessionLocal
from app.models.tenant import Tenant
from app.repositories.tenant_repository import TenantRepository


async def _main(tenant_id: str, name: str) -> None:
    async with SessionLocal() as session:
        repo = TenantRepository(session)
        if await repo.get(tenant_id) is not None:
            raise SystemExit(f"租户已存在：{tenant_id}")
        await repo.create(Tenant(id=tenant_id, name=name, status="active", plan="free"))
        await session.commit()
    print(f"已创建租户 id={tenant_id} name={name} plan=free")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="注册租户")
    parser.add_argument("--id", required=True, help="tenant_id，如 tenant_demo")
    parser.add_argument("--name", required=True, help="展示名")
    args = parser.parse_args()
    asyncio.run(_main(args.id, args.name))
