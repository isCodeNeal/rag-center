"""基于 Redis 的检索限流：秒级 QPS + 日检索量。

复用 Celery 的 Redis（settings.celery_broker_url），所有 key 加 `rag:` 前缀避免冲突。
- QPS：key = rag:ratelimit:retrieve:{tenant_id}:{unix_second}，TTL 2s，
  超过 plan.limits.retrieve_qps 抛 RetrieveRateLimited(20005)。
- 日检索量：key = rag:quota:retrieve:daily:{tenant_id}:{YYYYMMDD}，TTL 25h，
  超过 plan.limits.retrieve_daily 抛 QuotaExceeded(20014)。
  只在检索成功后 +1（record_retrieve_success），失败/被拒绝不计数。

check_retrieve 只读检查（QPS 用 INCR 占位，日配额用 GET 读当前值判断），
不在检查阶段给日计数 +1，避免失败请求也消耗配额。
"""
from __future__ import annotations

import time

from app.core.logging import get_logger
from app.core.exceptions import QuotaExceeded, RetrieveRateLimited
from app.tenant.plan_resolver import PlanContext

logger = get_logger(__name__)

_QPS_KEY = "rag:ratelimit:retrieve:{tenant_id}:{second}"
_DAILY_KEY = "rag:quota:retrieve:daily:{tenant_id}:{day}"
_DAILY_TTL_SECONDS = 25 * 3600  # 跨零点容错


def _day_str() -> str:
    return time.strftime("%Y%m%d", time.gmtime())


class RateLimitService:
    def __init__(self, redis_client):
        # redis_client：redis.asyncio.Redis（或任何实现 incr/expire/get 的 async 客户端）
        self._redis = redis_client

    async def check_retrieve(self, tenant_id: str, plan: PlanContext) -> None:
        """检索前的限流检查：先查日配额，再占用一次 QPS 窗口。"""
        # 1. 日检索量（只读判断，不在这里 +1）
        day_key = _DAILY_KEY.format(tenant_id=tenant_id, day=_day_str())
        current = await self._redis.get(day_key)
        used = int(current) if current is not None else 0
        if used >= plan.limits.retrieve_daily:
            raise QuotaExceeded(
                msg=f"已达当日检索上限（{plan.limits.retrieve_daily} 次/日），请明日再试或升级套餐",
                detail=f"tenant_id={tenant_id} daily={used}",
            )

        # 2. 秒级 QPS：INCR 当前秒窗口，首次设置 2s TTL。
        second = int(time.time())
        qps_key = _QPS_KEY.format(tenant_id=tenant_id, second=second)
        count = await self._redis.incr(qps_key)
        if count == 1:
            await self._redis.expire(qps_key, 2)
        if count > plan.limits.retrieve_qps:
            raise RetrieveRateLimited(
                msg="检索请求过于频繁，请稍后再试",
                detail=f"tenant_id={tenant_id} qps={count} limit={plan.limits.retrieve_qps}",
            )

    async def record_retrieve_success(self, tenant_id: str) -> None:
        """检索成功后给当日计数 +1。"""
        day_key = _DAILY_KEY.format(tenant_id=tenant_id, day=_day_str())
        count = await self._redis.incr(day_key)
        if count == 1:
            await self._redis.expire(day_key, _DAILY_TTL_SECONDS)

    async def get_daily_count(self, tenant_id: str) -> int:
        """读取当日检索计数（供 /auth/me usage 展示）。"""
        day_key = _DAILY_KEY.format(tenant_id=tenant_id, day=_day_str())
        current = await self._redis.get(day_key)
        return int(current) if current is not None else 0
