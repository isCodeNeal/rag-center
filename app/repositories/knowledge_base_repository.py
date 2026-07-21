"""KnowledgeBase 数据访问。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_base import KnowledgeBase


class KnowledgeBaseRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, kb: KnowledgeBase) -> KnowledgeBase:
        self._session.add(kb)
        await self._session.flush()
        return kb

    async def get(self, kb_id: str) -> KnowledgeBase | None:
        return await self._session.get(KnowledgeBase, kb_id)

    async def get_for_tenant(self, kb_id: str, tenant_id: str) -> KnowledgeBase | None:
        stmt = select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id, KnowledgeBase.tenant_id == tenant_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_tenant(
        self, tenant_id: str, keyword: str | None = None
    ) -> list[KnowledgeBase]:
        stmt = select(KnowledgeBase).where(KnowledgeBase.tenant_id == tenant_id)
        if keyword:
            stmt = stmt.where(KnowledgeBase.name.ilike(f"%{keyword}%"))
        stmt = stmt.order_by(KnowledgeBase.created_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
