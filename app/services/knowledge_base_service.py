"""知识库 service。"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.knowledge_base import KnowledgeBase
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.schemas.knowledge_base import (
    CreateKnowledgeBaseRequest,
    KnowledgeBaseData,
    KnowledgeTreeDoc,
    KnowledgeTreeKb,
    KnowledgeTreeTenant,
)
from app.utils.id_generator import new_kb_id

logger = get_logger(__name__)


class KnowledgeBaseService:
    def __init__(
        self,
        session: AsyncSession,
        kb_repository: KnowledgeBaseRepository,
        document_repository: DocumentRepository | None = None,
        chunk_repository: ChunkRepository | None = None,
    ):
        self._session = session
        self._kb_repo = kb_repository
        self._doc_repo = document_repository
        self._chunk_repo = chunk_repository

    async def create(self, req: CreateKnowledgeBaseRequest, tenant_id: str) -> KnowledgeBaseData:
        kb = KnowledgeBase(
            id=new_kb_id(),
            tenant_id=tenant_id,
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

    async def get_tree(
        self, tenant_id: str, keyword: str | None = None
    ) -> list[KnowledgeTreeTenant]:
        kbs = await self._kb_repo.list_by_tenant(tenant_id, keyword)
        kb_ids = [kb.id for kb in kbs]
        docs = await self._doc_repo.list_success_by_kb_ids(kb_ids) if kb_ids else []
        doc_ids = [d.id for d in docs]
        counts = await self._chunk_repo.count_by_document_ids(doc_ids) if doc_ids else {}

        docs_by_kb: dict[str, list[KnowledgeTreeDoc]] = {}
        for d in docs:
            docs_by_kb.setdefault(d.kb_id, []).append(
                KnowledgeTreeDoc(
                    document_id=d.id,
                    title=d.title,
                    status=d.status,
                    chunk_count=counts.get(d.id, 0),
                    created_at=d.created_at,
                )
            )

        if not kbs:
            return []
        tenant = KnowledgeTreeTenant(tenant_id=tenant_id, knowledge_bases=[])
        for kb in kbs:
            tenant.knowledge_bases.append(
                KnowledgeTreeKb(
                    kb_id=kb.id,
                    name=kb.name,
                    description=kb.description,
                    created_at=kb.created_at,
                    documents=docs_by_kb.get(kb.id, []),
                )
            )
        return [tenant]
