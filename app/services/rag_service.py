"""RAG 检索 service。

对 query 做 embedding，通过 VectorStore 抽象接口执行向量相似度检索；如果启用
rerank，则在召回之后调用 RerankProvider 对候选 chunk 重新打分排序；最后记录一条
retrieval log，并返回结构化的 chunk + metadata。这里不拼接 context_text，也不
调用生成模型 —— 由调用方自行编排各自的 LLM。
"""
from __future__ import annotations

import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import KnowledgeBaseNotFound, RerankError
from app.core.logging import get_logger
from app.models.retrieval_log import RetrievalLog
from app.providers.embedding.base import EmbeddingProvider
from app.providers.rerank.base import RerankProvider
from app.providers.rerank.llm import LLM_RERANK_PROVIDER_NAME
from app.providers.rerank.noop import NOOP_PROVIDER_NAME
from app.providers.vectorstores.base import VectorStore
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.repositories.retrieval_log_repository import RetrievalLogRepository
from app.schemas.rag import (
    RetrieveData,
    RetrieveMetadata,
    RetrieveRequest,
    RetrievedChunk,
)
from app.schemas.rerank import RerankMetadata
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
        rerank_provider: RerankProvider,
    ):
        self._session = session
        self._kb_repo = kb_repository
        self._log_repo = retrieval_log_repository
        self._embedding = embedding_provider
        self._vector_store = vector_store
        self._vector_store_name = vector_store_name
        self._rerank = rerank_provider

    async def retrieve(self, req: RetrieveRequest) -> RetrieveData:
        # 校验该租户下知识库是否存在
        kb = await self._kb_repo.get_for_tenant(req.kb_id, req.tenant_id)
        if kb is None:
            raise KnowledgeBaseNotFound(req.kb_id)

        top_k = req.top_k or settings.top_k
        rerank_enabled = self._resolve_rerank_enabled(req)
        top_n = self._resolve_top_n(req, top_k)
        started = time.perf_counter()

        # 1. 对 query 进行 embedding
        query_vector = await self._embedding.embed_query(req.query)

        # 2. 向量相似度检索（限定在 tenant + kb 范围内）
        hits = await self._vector_store.similarity_search(
            query_vector,
            tenant_id=req.tenant_id,
            kb_id=req.kb_id,
            top_k=top_k,
        )

        # 3. 为后续可能的 rerank 先转成统一 dict 结构（保留原始 vector score）
        candidates = [
            {
                "document_id": h["document_id"],
                "chunk_id": h["chunk_id"],
                "title": h["title"],
                "content": h["content"],
                "score": h["score"],
                "rerank_score": None,
            }
            for h in hits
        ]

        rerank_meta = RerankMetadata(enabled=rerank_enabled)
        final_chunks: list[dict[str, Any]]

        if rerank_enabled:
            # 优先以 top_k 召回候选，再由 rerank 决定最终 top_n；为了控制 token 成本，真正
            # 送入大模型的候选数量仍受 RERANK_MAX_CANDIDATES 限制（由 provider 内部处理）。
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
                # rerank 失败不让整个接口失败：记录日志并降级为原始向量排序结果。
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
        else:
            # 未启用 rerank：保持当前行为，但为了返回结构统一，metadata 仍带上 rerank 节点。
            rerank_meta.provider = self._rerank.name if self._rerank.name == NOOP_PROVIDER_NAME else None
            final_chunks = candidates[:top_n]

        latency_ms = int((time.perf_counter() - started) * 1000)

        retrieved = [
            RetrievedChunk(
                document_id=h["document_id"],
                chunk_id=h["chunk_id"],
                title=h["title"],
                content=h["content"],
                score=h["score"],
                rerank_score=h.get("rerank_score"),
            )
            for h in final_chunks
        ]

        # 4. 记录 retrieval log（尽力而为的可观测性埋点）
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
            "RAG_RETRIEVE | kb_id=%s | user_id=%s | top_k=%d | returned=%d | rerank=%s | cost=%dms",
            req.kb_id,
            req.user_id,
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
                rerank=rerank_meta,
            ),
        )

    def _resolve_rerank_enabled(self, req: RetrieveRequest) -> bool:
        # 请求级 rerank_options.enabled 优先级最高；不传时回退到系统配置。
        if req.rerank_options and req.rerank_options.enabled is not None:
            return req.rerank_options.enabled
        return settings.rerank_enabled

    def _resolve_top_n(self, req: RetrieveRequest, top_k: int) -> int:
        # 请求级 rerank_options.top_n > 系统配置；始终不超过 top_k，避免返回数量反超召回数量。
        top_n = (
            req.rerank_options.top_n
            if req.rerank_options and req.rerank_options.top_n is not None
            else settings.rerank_top_n
        )
        return min(top_n, top_k)
