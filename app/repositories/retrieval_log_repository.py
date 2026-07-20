"""RetrievalLog 数据访问。"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.retrieval_log import RetrievalLog


class RetrievalLogRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, log: RetrievalLog) -> RetrievalLog:
        self._session.add(log)
        await self._session.flush()
        return log
