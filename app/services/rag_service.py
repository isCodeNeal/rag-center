"""RAG retrieval service.

Embeds the query, runs vector similarity search via the VectorStore abstraction,
records a retrieval log, and returns structured chunks + metadata. It does NOT stitch
a context_text and does NOT call a generation model — callers orchestrate their own LLM.
"""
from __future__ import annotations

import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import KnowledgeBaseNotFound
from app.core.logging import get_logger
from app.models.retrieval_log import RetrievalLog
from app.providers.embedding.base import EmbeddingProvider
from app.providers.vectorstores.base import VectorStore
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.repositories.retrieval_log_repository import RetrievalLogRepository
from app.schemas.rag import (
    RetrieveData,
    RetrieveMetadata,
    RetrieveRequest,
    RetrievedChunk,
)
from app.utils.id_generator import new_retrieval_log_id

logger = get_logger(__name__)


class RAGService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        kb_repository: KnowledgeBaseRepository,
        retrieval_log_repository: RetrievalLogRepository,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
        vector_store_name: str,
    ):
        self._session = session
        self._kb_repo = kb_repository
        self._log_repo = retrieval_log_repository
        self._embedding = embedding_provider
        self._vector_store = vector_store
        self._vector_store_name = vector_store_name

    async def retrieve(self, req: RetrieveRequest) -> RetrieveData:
        # Validate the knowledge base exists for this tenant.
        kb = await self._kb_repo.get_for_tenant(req.kb_id, req.tenant_id)
        if kb is None:
            raise KnowledgeBaseNotFound(req.kb_id)

        top_k = req.top_k or settings.top_k
        started = time.perf_counter()

        # 1. Embed the query.
        query_vector = await self._embedding.embed_query(req.query)

        # 2. Vector similarity search (scoped to tenant + kb).
        hits = await self._vector_store.similarity_search(
            query_vector,
            tenant_id=req.tenant_id,
            kb_id=req.kb_id,
            top_k=top_k,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)

        retrieved = [
            RetrievedChunk(
                document_id=h["document_id"],
                chunk_id=h["chunk_id"],
                title=h["title"],
                content=h["content"],
                score=h["score"],
            )
            for h in hits
        ]

        # 3. Record the retrieval log (best-effort observability).
        log = RetrievalLog(
            id=new_retrieval_log_id(),
            tenant_id=req.tenant_id,
            kb_id=req.kb_id,
            user_id=req.user_id,
            query=req.query,
            retrieved_chunks=[c.model_dump() for c in retrieved],
            top_k=top_k,
            vector_store=self._vector_store_name,
            latency_ms=latency_ms,
        )
        await self._log_repo.create(log)
        await self._session.commit()

        logger.info(
            "RAG_RETRIEVE | kb_id=%s | user_id=%s | top_k=%d | hits=%d | cost=%dms",
            req.kb_id,
            req.user_id,
            top_k,
            len(retrieved),
            latency_ms,
        )
        return RetrieveData(
            query=req.query,
            kb_id=req.kb_id,
            retrieved_chunks=retrieved,
            metadata=RetrieveMetadata(
                top_k=top_k,
                vector_store=self._vector_store_name,
            ),
        )
