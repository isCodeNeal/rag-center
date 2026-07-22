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

    async def get_for_tenant(self, document_id: str, tenant_id: str) -> Document | None:
        stmt = select(Document).where(
            Document.id == document_id, Document.tenant_id == tenant_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_status(self, document: Document, status: int) -> Document:
        document.status = status
        await self._session.flush()
        return document

    async def delete(self, document: Document) -> None:
        await self._session.delete(document)
        await self._session.flush()

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

    async def list_by_kb_ids(self, kb_ids: list[str]) -> list[Document]:
        """列出这些 kb 下的全部文档（不过滤状态），供 tree 三态展示与删库使用。"""
        if not kb_ids:
            return []
        stmt = (
            select(Document)
            .where(Document.kb_id.in_(kb_ids))
            .order_by(Document.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_kb(self, kb_id: str) -> list[Document]:
        stmt = (
            select(Document)
            .where(Document.kb_id == kb_id)
            .order_by(Document.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
