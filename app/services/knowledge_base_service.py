"""Knowledge base service."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.knowledge_base import KnowledgeBase
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.schemas.knowledge_base import CreateKnowledgeBaseRequest, KnowledgeBaseData
from app.utils.id_generator import new_kb_id

logger = get_logger(__name__)


class KnowledgeBaseService:
    def __init__(self, session: AsyncSession, kb_repository: KnowledgeBaseRepository):
        self._session = session
        self._kb_repo = kb_repository

    async def create(self, req: CreateKnowledgeBaseRequest) -> KnowledgeBaseData:
        kb = KnowledgeBase(
            id=new_kb_id(),
            tenant_id=req.tenant_id,
            name=req.name,
            description=req.description,
        )
        await self._kb_repo.create(kb)
        await self._session.commit()
        await self._session.refresh(kb)
        logger.info("KB_CREATED | kb_id=%s | tenant_id=%s | name=%s", kb.id, kb.tenant_id, kb.name)
        return KnowledgeBaseData(
            kb_id=kb.id,
            name=kb.name,
            tenant_id=kb.tenant_id,
            created_at=kb.created_at,
        )
