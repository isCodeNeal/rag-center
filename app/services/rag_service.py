"""RAG 检索 service。

对 query 做 embedding，执行检索（向量 / BM25 / 混合），可选 RRF 融合和 LLM rerank，
最后记录 retrieval log，并返回结构化的 chunk + metadata。这里不拼接 context_text，
也不调用生成模型 —— 由调用方自行编排各自的 LLM。

【混合检索】
支持三种检索模式（可通过请求或配置指定）：
- vector: 纯向量召回（默认）
- bm25: 纯 BM25 关键词召回
- hybrid: 向量 + BM25 并行召回，RRF 融合排序

hybrid 模式下 BM25 失败会降级为纯向量结果，不影响接口可用性。
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import KeywordSearchError, KnowledgeBaseNotFound, RerankError
from app.core.logging import get_logger
from app.models.retrieval_log import RetrievalLog
from app.providers.embedding.base import EmbeddingProvider
from app.providers.keyword_search.base import KeywordSearchProvider
from app.providers.rerank.base import RerankProvider
from app.providers.rerank.llm import LLM_RERANK_PROVIDER_NAME
from app.providers.rerank.noop import NOOP_PROVIDER_NAME
from app.providers.vectorstores.base import VectorStore
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.repositories.retrieval_log_repository import RetrievalLogRepository
from app.schemas.hybrid_search import RetrievalMetadata as HybridRetrievalMetadata
from app.schemas.rag import (
    RetrieveData,
    RetrieveMetadata,
    RetrieveRequest,
    RetrievedChunk,
)
from app.schemas.rerank import RerankMetadata
from app.services.hybrid_search_service import HybridSearchService
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
        keyword_search_provider: KeywordSearchProvider | None,
        keyword_search_provider_name: str | None,
        rerank_provider: RerankProvider,
        hybrid_search_service: HybridSearchService,
    ):
        self._session = session
        self._kb_repo = kb_repository
        self._log_repo = retrieval_log_repository
        self._embedding = embedding_provider
        self._vector_store = vector_store
        self._vector_store_name = vector_store_name
        self._keyword_search = keyword_search_provider
        self._keyword_search_name = keyword_search_provider_name
        self._rerank = rerank_provider
        self._hybrid_search = hybrid_search_service

    async def retrieve(self, req: RetrieveRequest, tenant_id: str) -> RetrieveData:
        # 校验该租户下知识库是否存在
        kb = await self._kb_repo.get_for_tenant(req.kb_id, tenant_id)
        if kb is None:
            raise KnowledgeBaseNotFound(req.kb_id)

        retrieval_mode = self._resolve_retrieval_mode(req)
        top_k = req.top_k or settings.top_k
        rerank_enabled = self._resolve_rerank_enabled(req)
        top_n = self._resolve_top_n(req, top_k)
        started = time.perf_counter()

        logger.info(
            "HYBRID_SEARCH_START | kb_id=%s | user_id=%s | mode=%s | top_k=%d | rerank=%s",
            req.kb_id,
            req.user_id,
            retrieval_mode,
            top_k,
            rerank_enabled,
        )

        # 根据检索模式执行召回
        if retrieval_mode == "vector":
            candidates, retrieval_meta = await self._retrieve_vector_only(req, tenant_id, top_k)
        elif retrieval_mode == "bm25":
            candidates, retrieval_meta = await self._retrieve_bm25_only(req, tenant_id, top_k)
        else:  # hybrid
            candidates, retrieval_meta = await self._retrieve_hybrid(req, tenant_id)

        # 可选 rerank 阶段（精排）
        rerank_meta = RerankMetadata(enabled=rerank_enabled)
        final_chunks = await self._apply_rerank(candidates, req, rerank_enabled, top_n, rerank_meta)

        latency_ms = int((time.perf_counter() - started) * 1000)

        # 组装响应
        retrieved = [
            RetrievedChunk(
                document_id=h["document_id"],
                chunk_id=h["chunk_id"],
                title=h["title"],
                content=h["content"],
                score=h["score"],
                vector_score=h.get("vector_score"),
                bm25_score=h.get("bm25_score"),
                vector_rank=h.get("vector_rank"),
                bm25_rank=h.get("bm25_rank"),
                retrieval_source=h.get("retrieval_source"),
                rerank_score=h.get("rerank_score"),
            )
            for h in final_chunks
        ]

        # 记录 retrieval log（尽力而为的可观测性埋点）
        log = RetrievalLog(
            id=new_retrieval_log_id(),
            tenant_id=tenant_id,
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
            "RAG_RETRIEVE | kb_id=%s | user_id=%s | mode=%s | top_k=%d | returned=%d | rerank=%s | cost=%dms",
            req.kb_id,
            req.user_id,
            retrieval_mode,
            top_k,
            len(retrieved),
            rerank_enabled,
            latency_ms,
        )
        return RetrieveData(
            query=req.query,
            kb_id=req.kb_id,
            retrieved_chunks=retrieved,
            metadata=RetrieveMetadata(
                top_k=top_k,
                vector_store=self._vector_store_name,
                latency_ms=latency_ms,
                retrieval=retrieval_meta,
                rerank=rerank_meta,
            ),
        )

    async def _retrieve_vector_only(
        self, req: RetrieveRequest, tenant_id: str, top_k: int
    ) -> tuple[list[dict[str, Any]], HybridRetrievalMetadata]:
        query_vector = await self._embedding.embed_query(req.query)
        hits = await self._vector_store.similarity_search(
            query_vector,
            tenant_id=tenant_id,
            kb_id=req.kb_id,
            top_k=top_k,
        )
        logger.info("VECTOR_SEARCH_SUCCESS | kb_id=%s | count=%d", req.kb_id, len(hits))

        candidates = [
            {
                "document_id": h["document_id"],
                "chunk_id": h["chunk_id"],
                "title": h["title"],
                "content": h["content"],
                "score": h["score"],
                "vector_score": h["score"],
                "retrieval_source": "vector",
            }
            for h in hits
        ]
        meta = HybridRetrievalMetadata(
            mode="vector",
            vector_store=self._vector_store_name,
            vector_count=len(candidates),
        )
        return candidates, meta

    async def _retrieve_bm25_only(
        self, req: RetrieveRequest, tenant_id: str, top_k: int
    ) -> tuple[list[dict[str, Any]], HybridRetrievalMetadata]:
        if self._keyword_search is None:
            raise KeywordSearchError("keyword search provider not configured")

        hits = await self._keyword_search.keyword_search(
            query=req.query,
            tenant_id=tenant_id,
            kb_id=req.kb_id,
            top_k=top_k,
        )
        logger.info("BM25_SEARCH_SUCCESS | kb_id=%s | count=%d", req.kb_id, len(hits))

        candidates = [
            {
                "document_id": h["document_id"],
                "chunk_id": h["chunk_id"],
                "title": h["title"],
                "content": h["content"],
                "score": h["bm25_score"],
                "bm25_score": h["bm25_score"],
                "retrieval_source": "bm25",
            }
            for h in hits
        ]
        meta = HybridRetrievalMetadata(
            mode="bm25",
            keyword_search=self._keyword_search_name,
            bm25_count=len(candidates),
        )
        return candidates, meta

    async def _retrieve_hybrid(
        self, req: RetrieveRequest, tenant_id: str
    ) -> tuple[list[dict[str, Any]], HybridRetrievalMetadata]:
        if self._keyword_search is None:
            raise KeywordSearchError("keyword search provider not configured for hybrid mode")

        vector_top_k = (
            req.retrieval_options.vector_top_k
            if req.retrieval_options and req.retrieval_options.vector_top_k
            else settings.hybrid_vector_top_k
        )
        bm25_top_k = (
            req.retrieval_options.bm25_top_k
            if req.retrieval_options and req.retrieval_options.bm25_top_k
            else settings.hybrid_bm25_top_k
        )
        rrf_k = (
            req.retrieval_options.rrf_k
            if req.retrieval_options and req.retrieval_options.rrf_k
            else settings.hybrid_rrf_k
        )

        # 并行执行向量召回和 BM25 召回
        query_vector = await self._embedding.embed_query(req.query)
        vector_task = self._vector_store.similarity_search(
            query_vector, tenant_id=tenant_id, kb_id=req.kb_id, top_k=vector_top_k
        )
        bm25_task = self._keyword_search.keyword_search(
            query=req.query, tenant_id=tenant_id, kb_id=req.kb_id, top_k=bm25_top_k
        )

        vector_hits, bm25_hits = None, None
        bm25_failed = False
        try:
            vector_hits, bm25_hits = await asyncio.gather(vector_task, bm25_task)
            logger.info(
                "VECTOR_SEARCH_SUCCESS | kb_id=%s | count=%d", req.kb_id, len(vector_hits)
            )
            logger.info("BM25_SEARCH_SUCCESS | kb_id=%s | count=%d", req.kb_id, len(bm25_hits))
        except KeywordSearchError as exc:
            # BM25 失败不影响主链路：记录日志并降级为纯向量结果。
            logger.error(
                "BM25_SEARCH_FAILED | kb_id=%s | user_id=%s | error=%s",
                req.kb_id,
                req.user_id,
                str(exc),
            )
            bm25_failed = True
            vector_hits = await vector_task  # 确保向量召回完成

        # RRF 融合
        if bm25_failed or bm25_hits is None:
            # 降级为纯向量结果
            candidates = [
                {
                    "document_id": h["document_id"],
                    "chunk_id": h["chunk_id"],
                    "title": h["title"],
                    "content": h["content"],
                    "score": h["score"],
                    "vector_score": h["score"],
                    "retrieval_source": "vector",
                }
                for h in vector_hits or []
            ]
            meta = HybridRetrievalMetadata(
                mode="hybrid",
                fusion="rrf",
                rrf_k=rrf_k,
                vector_store=self._vector_store_name,
                keyword_search=self._keyword_search_name,
                vector_top_k=vector_top_k,
                bm25_top_k=bm25_top_k,
                vector_count=len(vector_hits) if vector_hits else 0,
                bm25_count=0,
                degraded=True,
                degraded_reason="bm25 search failed",
            )
            logger.warning("HYBRID_SEARCH_DEGRADED | kb_id=%s | reason=bm25_failed", req.kb_id)
        else:
            # 正常 RRF 融合
            fused = self._hybrid_search.fuse_rrf(
                vector_chunks=vector_hits,
                bm25_chunks=bm25_hits,
                top_n=settings.hybrid_top_n,
            )
            logger.info(
                "RRF_FUSION_SUCCESS | kb_id=%s | vector_count=%d | bm25_count=%d | fused_count=%d",
                req.kb_id,
                len(vector_hits),
                len(bm25_hits),
                len(fused),
            )
            candidates = fused
            meta = HybridRetrievalMetadata(
                mode="hybrid",
                fusion="rrf",
                rrf_k=rrf_k,
                vector_store=self._vector_store_name,
                keyword_search=self._keyword_search_name,
                vector_top_k=vector_top_k,
                bm25_top_k=bm25_top_k,
                vector_count=len(vector_hits),
                bm25_count=len(bm25_hits),
                fused_count=len(fused),
            )

        return candidates, meta

    async def _apply_rerank(
        self,
        candidates: list[dict[str, Any]],
        req: RetrieveRequest,
        rerank_enabled: bool,
        top_n: int,
        rerank_meta: RerankMetadata,
    ) -> list[dict[str, Any]]:
        if not rerank_enabled:
            rerank_meta.provider = self._rerank.name if self._rerank.name == NOOP_PROVIDER_NAME else None
            return candidates[:top_n]

        rerank_meta.provider = self._rerank.name
        rerank_meta.top_n = top_n
        rerank_meta.candidate_count = min(len(candidates), settings.rerank_max_candidates)
        if self._rerank.name == LLM_RERANK_PROVIDER_NAME:
            rerank_meta.llm_provider = settings.llm_provider
            rerank_meta.model = settings.llm_model

        try:
            final_chunks = await self._rerank.rerank(
                query=req.query,
                chunks=candidates,
                top_n=top_n,
            )
        except RerankError as exc:
            # rerank 失败不让整个接口失败：记录日志并降级为原始排序结果。
            rerank_meta.degraded = True
            rerank_meta.error = exc.detail or exc.msg
            logger.error(
                "RERANK_DEGRADED | kb_id=%s | user_id=%s | error=%s",
                req.kb_id,
                req.user_id,
                rerank_meta.error,
            )
            final_chunks = candidates[:top_n]
        else:
            logger.info(
                "RERANK_OK | kb_id=%s | user_id=%s | provider=%s | top_n=%d | candidates=%d",
                req.kb_id,
                req.user_id,
                self._rerank.name,
                top_n,
                rerank_meta.candidate_count or len(candidates),
            )
        return final_chunks

    def _resolve_retrieval_mode(self, req: RetrieveRequest) -> str:
        if req.retrieval_options and req.retrieval_options.mode is not None:
            return req.retrieval_options.mode
        return settings.retrieval_mode

    def _resolve_rerank_enabled(self, req: RetrieveRequest) -> bool:
        if req.rerank_options and req.rerank_options.enabled is not None:
            return req.rerank_options.enabled
        return settings.rerank_enabled

    def _resolve_top_n(self, req: RetrieveRequest, top_k: int) -> int:
        top_n = (
            req.rerank_options.top_n
            if req.rerank_options and req.rerank_options.top_n is not None
            else settings.rerank_top_n
        )
        return min(top_n, top_k)
