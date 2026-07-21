"""Document 数据访问。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.enums import DocumentStatus


class DocumentRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, document: Document) -> Document:
        self._session.add(document)
        await self._session.flush()
        return document

    async def get(self, document_id: str) -> Document | None:
        return await self._session.get(Document, document_id)

    async def update_status(self, document: Document, status: int) -> Document:
        document.status = status
        await self._session.flush()
        return document

    async def list_success_by_kb_ids(self, kb_ids: list[str]) -> list[Document]:
        if not kb_ids:
            return []
        stmt = (
            select(Document)
            .where(
                Document.kb_id.in_(kb_ids),
                Document.status == DocumentStatus.SUCCESS.value,
            )
            .order_by(Document.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
