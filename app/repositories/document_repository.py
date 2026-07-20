"""Document data access."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document


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
