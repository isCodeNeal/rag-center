"""修改租户套餐档位：python scripts/update_tenant_plan.py --tenant-id tenant_a --plan pro。

plan 必须是 free / standard / pro，传非法值报错退出。
tenant 不存在时提示先运行 create_tenant。
"""
from __future__ import annotations

import argparse
import asyncio

from app.db.session import SessionLocal
from app.repositories.tenant_repository import TenantRepository
from app.tenant.plan_presets import VALID_PLANS


async def _main(tenant_id: str, plan: str) -> None:
    if plan not in VALID_PLANS:
        raise SystemExit(f"非法 plan：{plan}，可选值：{', '.join(VALID_PLANS)}")

    async with SessionLocal() as session:
        repo = TenantRepository(session)
        tenant = await repo.get(tenant_id)
        if tenant is None:
            raise SystemExit(
                f"租户不存在：{tenant_id}，请先运行 scripts/create_tenant.py 创建"
            )
        tenant.plan = plan
        await session.commit()
    print(f"已更新租户 id={tenant_id} plan={plan}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="修改租户套餐档位")
    parser.add_argument("--tenant-id", required=True, help="已存在的租户 id")
    parser.add_argument(
        "--plan", required=True, help="套餐档位：free / standard / pro"
    )
    args = parser.parse_args()
    asyncio.run(_main(args.tenant_id, args.plan))
