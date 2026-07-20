"""VectorStore abstraction.

Stage 1 ships PgVectorStore, but no service depends on pgvector directly — only on
this interface. Later stores (Milvus, Qdrant, Elastic) implement the same contract.

Chunk dicts flowing through `add_chunks` are expected to contain:
    id, tenant_id, kb_id, document_id, title, content, metadata, embedding

`similarity_search` returns dicts containing:
    document_id, chunk_id, title, content, score
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class VectorStore(ABC):
    @abstractmethod
    async def add_chunks(self, chunks: list[dict[str, Any]]) -> None:
        """Persist chunks (with embeddings) into the store."""
        raise NotImplementedError

    @abstractmethod
    async def similarity_search(
        self,
        query_vector: list[float],
        *,
        tenant_id: str,
        kb_id: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Return the top_k most similar chunks scoped to tenant_id + kb_id."""
        raise NotImplementedError

    @abstractmethod
    async def delete_by_document_id(self, document_id: str) -> None:
        """Delete all chunks belonging to a document (used on re-index/cleanup)."""
        raise NotImplementedError
