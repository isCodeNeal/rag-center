"""Chunk 数据访问，包括基于 pgvector 的相似度检索。

pgvector 相关的 SQL（按 cosine distance 排序）由这个 repository 负责。PgVectorStore
适配器把调用委托到这里，从而保证原始 DB 访问始终留在 repository 层。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk


class ChunkRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def bulk_insert(self, chunks: list[dict[str, Any]]) -> None:
        """插入 chunk 行。每个 dict 包含 id/tenant_id/kb_id/document_id/
        title/content/metadata/embedding。"""
        objects = [
            Chunk(
                id=c["id"],
                tenant_id=c["tenant_id"],
                kb_id=c["kb_id"],
                document_id=c["document_id"],
                title=c["title"],
                content=c["content"],
                chunk_metadata=c.get("metadata"),
                embedding=c["embedding"],
            )
            for c in chunks
        ]
        self._session.add_all(objects)
        await self._session.flush()

    async def similarity_search(
        self,
        query_vector: list[float],
        *,
        tenant_id: str,
        kb_id: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        # cosine distance 取值范围 [0, 2]；similarity score = 1 - distance
        distance = Chunk.embedding.cosine_distance(query_vector).label("distance")
        stmt = (
            select(Chunk, distance)
            .where(Chunk.tenant_id == tenant_id, Chunk.kb_id == kb_id)
            .order_by(distance.asc())
            .limit(top_k)
        )
        result = await self._session.execute(stmt)
        rows = result.all()

        out: list[dict[str, Any]] = []
        for chunk, dist in rows:
            out.append(
                {
                    "document_id": chunk.document_id,
                    "chunk_id": chunk.id,
                    "title": chunk.title,
                    "content": chunk.content,
                    "score": round(1.0 - float(dist), 6),
                }
            )
        return out

    async def delete_by_document_id(self, document_id: str) -> None:
        await self._session.execute(
            delete(Chunk).where(Chunk.document_id == document_id)
        )
        await self._session.flush()

    async def count_by_document_ids(self, document_ids: list[str]) -> dict[str, int]:
        if not document_ids:
            return {}
        stmt = (
            select(Chunk.document_id, func.count().label("cnt"))
            .where(Chunk.document_id.in_(document_ids))
            .group_by(Chunk.document_id)
        )
        result = await self._session.execute(stmt)
        return {document_id: int(cnt) for document_id, cnt in result.all()}
