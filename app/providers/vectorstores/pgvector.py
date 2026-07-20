"""pgvector-backed VectorStore.

Thin adapter over ChunkRepository: it keeps all raw DB access in the repository layer
while exposing the store-agnostic VectorStore contract to services. Cosine similarity
is used; score = 1 - cosine_distance.
"""
from __future__ import annotations

from typing import Any

from app.core.exceptions import VectorStoreError
from app.core.logging import get_logger
from app.providers.vectorstores.base import VectorStore
from app.repositories.chunk_repository import ChunkRepository

logger = get_logger(__name__)

VECTOR_STORE_NAME = "pgvector"


class PgVectorStore(VectorStore):
    def __init__(self, chunk_repository: ChunkRepository):
        self._chunks = chunk_repository

    @property
    def name(self) -> str:
        return VECTOR_STORE_NAME

    async def add_chunks(self, chunks: list[dict[str, Any]]) -> None:
        if not chunks:
            return
        try:
            await self._chunks.bulk_insert(chunks)
        except Exception as exc:  # noqa: BLE001 - surface as domain error
            logger.error("pgvector add_chunks failed: %s", exc)
            raise VectorStoreError(f"failed to write chunks to pgvector: {exc}")

    async def similarity_search(
        self,
        query_vector: list[float],
        *,
        tenant_id: str,
        kb_id: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        try:
            return await self._chunks.similarity_search(
                query_vector, tenant_id=tenant_id, kb_id=kb_id, top_k=top_k
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("pgvector similarity_search failed: %s", exc)
            raise VectorStoreError(f"pgvector similarity search failed: {exc}")

    async def delete_by_document_id(self, document_id: str) -> None:
        try:
            await self._chunks.delete_by_document_id(document_id)
        except Exception as exc:  # noqa: BLE001
            logger.error("pgvector delete_by_document_id failed: %s", exc)
            raise VectorStoreError(f"pgvector delete failed: {exc}")
