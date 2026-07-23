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

【多库并行召回】
传入 kb_ids 列表时，对每个库并行执行召回，再用跨库 RRF 融合后返回综合 top_k。
单库路径（kb_ids 长度为 1）保持与原逻辑完全一致。
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import KeywordSearchError, KnowledgeBaseNotFound, RerankError
from app.core.exceptions import FeatureNotAllowed
from app.core.error_codes import ErrorCode
from app.core.exceptions import raise_error
from app.core.logging import get_logger
from app.models.retrieval_log import RetrievalLog
from app.observability.langfuse_client import RetrieveObservability
from app.providers.embedding.base import EmbeddingProvider
from app.providers.keyword_search.base import KeywordSearchProvider
from app.providers.rerank.base import RerankProvider
from app.providers.rerank.llm import LLM_RERANK_PROVIDER_NAME
from app.providers.rerank.noop import NOOP_PROVIDER_NAME
from app.providers.vectorstores.base import VectorStore
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.repositories.retrieval_log_repository import RetrievalLogRepository
from app.schemas.hybrid_search import RetrievalMetadata as HybridRetrievalMetadata
from app.providers.query.base import QueryProcessResult
from app.providers.query.pipeline import QueryPipeline
from app.schemas.rag import (
    QueryProcessing,
    RetrieveData,
    RetrieveMetadata,
    RetrieveRequest,
    RetrievedChunk,
    TenantPolicy,
)
from app.schemas.rerank import RerankMetadata
from app.services.hybrid_search_service import HybridSearchService
from app.tenant.plan_resolver import resolve_plan
from app.tenant.retrieve_presets import (
    DEFAULT_PROFILE,
    PROFILE_CUSTOM,
    RETRIEVE_PROFILE_PRESETS,
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
        keyword_search_provider: KeywordSearchProvider | None,
        keyword_search_provider_name: str | None,
        rerank_provider: RerankProvider,
        hybrid_search_service: HybridSearchService,
        query_pipeline: QueryPipeline,
        rate_limit_service=None,
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
        self._query_pipeline = query_pipeline
        self._rate_limit = rate_limit_service

    async def retrieve(
        self, req: RetrieveRequest, tenant_id: str, plan: str = "free"
    ) -> RetrieveData:
        # 解析 kb_ids（兼容单 kb_id）
        kb_ids: list[str] = req.kb_ids if req.kb_ids else ([req.kb_id] if req.kb_id else [])
        if not kb_ids:
            raise_error(ErrorCode.PARAM_ERROR, msg="kb_id 或 kb_ids 不能为空")

        # plan 校验多库上限
        plan_ctx = resolve_plan(plan)
        max_kb = min(plan_ctx.limits.max_kb_per_retrieve, settings.multi_kb_max)
        if len(kb_ids) > max_kb:
            raise FeatureNotAllowed(
                msg=f"当前套餐（{plan_ctx.plan}）最多支持 {max_kb} 个库联合检索",
                detail=f"kb_ids count={len(kb_ids)} max={max_kb}",
            )

        # 校验所有 KB 归属当前 tenant（并行查询）
        kbs_results = await asyncio.gather(
            *[self._kb_repo.get_for_tenant(kid, tenant_id) for kid in kb_ids]
        )
        for kb, kid in zip(kbs_results, kb_ids):
            if kb is None:
                raise KnowledgeBaseNotFound(kid)

        kb_map = {kb.id: kb for kb in kbs_results}  # id -> KB 对象

        # 解析 plan，校验 profile，展开成生效参数并校验是否超出 plan 上限。
        profile, retrieval_mode, top_k, rerank_enabled, rewrite_enabled = (
            self._resolve_profile_and_options(req, plan_ctx)
        )

        # QPS / 日配额限流（限流失败在检索前抛出，不消耗日计数）。
        if self._rate_limit is not None:
            await self._rate_limit.check_retrieve(tenant_id, plan_ctx)

        # Langfuse trace 开启（LANGFUSE_ENABLED=false 时静默无操作）
        obs = RetrieveObservability(
            metadata={
                "tenant_id": tenant_id,
                "kb_id": kb_ids[0],
                "kb_ids": kb_ids,
                "user_id": req.user_id,
                "profile": profile,
                "plan": plan_ctx.plan,
            }
        )

        # 提问语义优化：改写（可选）+ 词表扩展（有 settings 即尝试）。
        # 使用 kb_ids[0] 的 name/description 参与改写提示。
        first_kb = kb_map[kb_ids[0]]
        qp = await self._query_pipeline.run(
            req.query,
            rewrite_enabled=rewrite_enabled,
            kb_name=first_kb.name,
            kb_description=first_kb.description,
            kb_settings=first_kb.settings or {},
        )
        search_query = qp.search_query

        obs.record_query_processing(
            raw_query=qp.raw_query,
            effective_query=qp.effective_query,
            search_query=qp.search_query,
            synonym_applied=qp.synonym_applied,
            synonym_expansions=qp.synonym_expansions,
            degraded=qp.degraded,
        )

        top_n = self._resolve_top_n(req, top_k)
        started = time.perf_counter()

        logger.info(
            "HYBRID_SEARCH_START | kb_ids=%s | user_id=%s | plan=%s | profile=%s | mode=%s | top_k=%d | rerank=%s",
            kb_ids,
            req.user_id,
            plan_ctx.plan,
            profile,
            retrieval_mode,
            top_k,
            rerank_enabled,
        )

        # 根据库数量走单库或多库路径
        if len(kb_ids) == 1:
            # 单库路径：完全复用现有逻辑
            if retrieval_mode == "vector":
                candidates, retrieval_meta = await self._retrieve_vector_only(
                    req, tenant_id, top_k, search_query, kb_id=kb_ids[0]
                )
            elif retrieval_mode == "bm25":
                candidates, retrieval_meta = await self._retrieve_bm25_only(
                    req, tenant_id, top_k, search_query, kb_id=kb_ids[0]
                )
            else:  # hybrid
                candidates, retrieval_meta = await self._retrieve_hybrid(
                    req, tenant_id, search_query, kb_id=kb_ids[0]
                )
        else:
            # 多库路径：并行召回 + 跨库 RRF 融合
            candidates, retrieval_meta = await self._retrieve_multi_kb(
                req, tenant_id, top_k, search_query,
                kb_ids=kb_ids, kb_map=kb_map, retrieval_mode=retrieval_mode,
            )

        obs.record_retrieval(
            mode=retrieval_meta.mode,
            vector_count=retrieval_meta.vector_count,
            bm25_count=retrieval_meta.bm25_count,
            fused_count=retrieval_meta.fused_count,
            degraded=retrieval_meta.degraded,
        )

        # 可选 rerank 阶段（精排）
        rerank_meta = RerankMetadata(enabled=rerank_enabled)
        final_chunks = await self._apply_rerank(candidates, req, rerank_enabled, top_n, rerank_meta)

        obs.record_rerank(
            enabled=rerank_meta.enabled,
            candidate_count=rerank_meta.candidate_count,
            degraded=rerank_meta.degraded,
        )

        latency_ms = int((time.perf_counter() - started) * 1000)

        # 组装响应（带 kb_id / kb_name 来源信息）
        retrieved = [
            RetrievedChunk(
                document_id=h["document_id"],
                chunk_id=h["chunk_id"],
                title=h["title"],
                content=h["content"],
                score=h["score"],
                kb_id=h.get("kb_id"),
                kb_name=h.get("kb_name"),
                vector_score=h.get("vector_score"),
                bm25_score=h.get("bm25_score"),
                vector_rank=h.get("vector_rank"),
                bm25_rank=h.get("bm25_rank"),
                retrieval_source=h.get("retrieval_source"),
                rerank_score=h.get("rerank_score"),
            )
            for h in final_chunks
        ]

        # Langfuse trace 写入，返回 trace_id（失败时返回 None，不影响主流程）
        chunk_summaries = [
            {"chunk_id": c.chunk_id, "score": c.score} for c in retrieved[:10]
        ]
        trace_id = obs.finish(chunk_summaries=chunk_summaries)

        # 记录 retrieval log；log.id 作为 log_id 返回给调用方
        log_id = new_retrieval_log_id()
        # 多库时 kb_ids 字段记录完整列表；单库时保持向后兼容不写 kb_ids
        log_kb_ids = kb_ids if len(kb_ids) > 1 else None
        log = RetrievalLog(
            id=log_id,
            tenant_id=tenant_id,
            kb_id=kb_ids[0],
            kb_ids=log_kb_ids,
            user_id=req.user_id,
            query=req.query,
            effective_query=qp.effective_query,
            search_query=qp.search_query,
            trace_id=trace_id,
            profile=profile,
            retrieved_chunks=[c.model_dump() for c in retrieved],
            top_k=top_k,
            vector_store=self._vector_store_name,
            latency_ms=latency_ms,
        )
        await self._log_repo.create(log)
        await self._session.commit()

        # 检索成功后给当日计数 +1（被拒绝/失败的请求不会走到这里）。
        if self._rate_limit is not None:
            await self._rate_limit.record_retrieve_success(tenant_id)

        logger.info(
            "RAG_RETRIEVE | kb_ids=%s | user_id=%s | mode=%s | top_k=%d | returned=%d | rerank=%s | cost=%dms | log_id=%s | trace_id=%s",
            kb_ids,
            req.user_id,
            retrieval_mode,
            top_k,
            len(retrieved),
            rerank_enabled,
            latency_ms,
            log_id,
            trace_id,
        )
        tenant_policy = TenantPolicy(
            plan=plan_ctx.plan,
            retrieve_profile=profile,
            effective_mode=retrieval_mode,
            effective_rerank=rerank_enabled,
            effective_query_rewrite=rewrite_enabled,
        )
        return RetrieveData(
            query=req.query,
            kb_id=kb_ids[0],
            kb_ids=kb_ids,
            retrieved_chunks=retrieved,
            metadata=RetrieveMetadata(
                top_k=top_k,
                vector_store=self._vector_store_name,
                latency_ms=latency_ms,
                log_id=log_id,
                trace_id=trace_id,
                retrieval=retrieval_meta,
                rerank=rerank_meta,
                query_processing=self._build_query_processing(qp),
                tenant_policy=tenant_policy,
            ),
        )

    async def _retrieve_multi_kb(
        self,
        req: RetrieveRequest,
        tenant_id: str,
        top_k: int,
        search_query: str,
        *,
        kb_ids: list[str],
        kb_map: dict,
        retrieval_mode: str,
    ) -> tuple[list[dict[str, Any]], HybridRetrievalMetadata]:
        """并行对每个 kb 执行召回，然后跨库 RRF 融合，返回 top_k 结果。

        单个库召回失败时记录日志但不整体失败，其余库结果照常参与融合。
        """
        per_kb_top_k = max(top_k, settings.hybrid_vector_top_k, 10)

        tasks = [
            self._retrieve_candidates_for_kb(
                req, tenant_id, per_kb_top_k, search_query,
                kb_id=kid, retrieval_mode=retrieval_mode,
            )
            for kid in kb_ids
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_candidates: list[list[dict]] = []
        for kid, result in zip(kb_ids, results):
            if isinstance(result, Exception):
                logger.error(
                    "MULTI_KB_RETRIEVE_FAILED | kb_id=%s | error=%s", kid, result
                )
                continue
            kb_candidates, _ = result
            kb_name = kb_map[kid].name if kid in kb_map else kid
            for c in kb_candidates:
                c["kb_id"] = kid
                c["kb_name"] = kb_name
            all_candidates.append(kb_candidates)

        fused = self._fuse_multi_kb_rrf(all_candidates, top_n=top_k, rrf_k=settings.hybrid_rrf_k)

        logger.info(
            "MULTI_KB_RRF_FUSION | kb_ids=%s | per_kb_top_k=%d | fused_count=%d",
            kb_ids, per_kb_top_k, len(fused),
        )

        meta = HybridRetrievalMetadata(
            mode=retrieval_mode,
            multi_kb=True,
            kb_count=len(kb_ids),
            per_kb_top_k=per_kb_top_k,
            fusion="rrf",
            rrf_k=settings.hybrid_rrf_k,
            fused_count=len(fused),
        )
        return fused, meta

    def _fuse_multi_kb_rrf(
        self,
        kb_candidates_list: list[list[dict]],
        *,
        top_n: int,
        rrf_k: int,
    ) -> list[dict]:
        """跨库 RRF 融合。

        每库内按排名计算 RRF 分（1 / (rrf_k + rank)），按 chunk_id 累加。
        同一 chunk 若在多库中命中，分数叠加（理论上不同库的 chunk_id 不重叠，
        但 RRF 累加设计对此情况仍正确处理）。
        """
        scores: dict[str, float] = {}
        chunk_data: dict[str, dict] = {}

        for kb_candidates in kb_candidates_list:
            for rank, chunk in enumerate(kb_candidates, start=1):
                cid = chunk["chunk_id"]
                rrf_score = 1.0 / (rrf_k + rank)
                scores[cid] = scores.get(cid, 0.0) + rrf_score
                if cid not in chunk_data:
                    chunk_data[cid] = chunk

        sorted_ids = sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)
        result = []
        for cid in sorted_ids[:top_n]:
            c = dict(chunk_data[cid])
            c["score"] = scores[cid]
            result.append(c)
        return result

    async def _retrieve_candidates_for_kb(
        self,
        req: RetrieveRequest,
        tenant_id: str,
        top_k: int,
        search_query: str,
        *,
        kb_id: str,
        retrieval_mode: str,
    ) -> tuple[list[dict[str, Any]], HybridRetrievalMetadata]:
        """对单个 kb 执行指定模式的召回，供多库并行路径调用。"""
        if retrieval_mode == "vector":
            return await self._retrieve_vector_only(req, tenant_id, top_k, search_query, kb_id=kb_id)
        elif retrieval_mode == "bm25":
            return await self._retrieve_bm25_only(req, tenant_id, top_k, search_query, kb_id=kb_id)
        else:
            return await self._retrieve_hybrid(req, tenant_id, search_query, kb_id=kb_id)

    def _resolve_profile_and_options(
        self, req: RetrieveRequest, plan_ctx
    ) -> tuple[str, str, int, bool, bool]:
        """按 plan 校验 profile，展开成 (profile, mode, top_k, rerank_enabled, rewrite_enabled)。

        - profile 未传默认 balanced。
        - profile 不在 plan 允许列表 → FeatureNotAllowed(20013)。
        - profile 非 custom → 按 retrieve_presets 展开固定 options。
        - custom → 用请求里已有的 options（受下面 plan 上限约束）。
        - plan ceiling 优先于 .env 全局开关：功能不允许时强制关闭，
          若 custom 主动开启了不允许的能力 → FeatureNotAllowed。
        """
        profile = req.profile or DEFAULT_PROFILE
        if profile not in plan_ctx.features.allowed_profiles:
            raise FeatureNotAllowed(
                msg=f"当前套餐（{plan_ctx.plan}）不支持 {profile} 检索档位，请升级套餐",
                detail=f"profile={profile} allowed={plan_ctx.features.allowed_profiles}",
            )

        if profile != PROFILE_CUSTOM:
            preset = RETRIEVE_PROFILE_PRESETS[profile]
            mode = preset["mode"]
            top_k = preset["top_k"]
            rerank_enabled = preset["rerank_enabled"]
            rewrite_enabled = preset["query_rewrite_enabled"]
        else:
            # custom：用请求里已有的 options（回退到 .env 全局默认）。
            mode = self._resolve_retrieval_mode(req)
            top_k = req.top_k or settings.top_k
            rerank_enabled = self._resolve_rerank_enabled(req)
            rewrite_enabled = self._resolve_rewrite_enabled(req)

        # plan ceiling 校验：任何被展开/请求打开的能力都不能超出 plan 上限。
        if mode == "hybrid" and not plan_ctx.features.hybrid_allowed:
            if profile == PROFILE_CUSTOM:
                raise FeatureNotAllowed(
                    msg=f"当前套餐（{plan_ctx.plan}）不支持 hybrid 检索，请升级套餐",
                    detail="hybrid not allowed",
                )
            mode = "vector"  # preset 理论上不会触发，防御性降级
        if rerank_enabled and not plan_ctx.features.rerank_allowed:
            if profile == PROFILE_CUSTOM:
                raise FeatureNotAllowed(
                    msg=f"当前套餐（{plan_ctx.plan}）不支持 rerank，请升级套餐",
                    detail="rerank not allowed",
                )
            rerank_enabled = False
        if rewrite_enabled and not plan_ctx.features.query_rewrite_allowed:
            if profile == PROFILE_CUSTOM:
                raise FeatureNotAllowed(
                    msg=f"当前套餐（{plan_ctx.plan}）不支持 query 改写，请升级套餐",
                    detail="query_rewrite not allowed",
                )
            rewrite_enabled = False

        return profile, mode, top_k, rerank_enabled, rewrite_enabled

    @staticmethod
    def _build_query_processing(qp: QueryProcessResult) -> QueryProcessing | None:
        # 有实际处理（改写、词表命中，或 search_query 与原话不同）时才返回；
        # 全无处理时返回 None，保持与改造前兼容。
        touched = (
            qp.strategy != "noop"
            or qp.synonym_applied
            or qp.search_query != qp.raw_query
        )
        if not touched:
            return None
        return QueryProcessing(
            raw_query=qp.raw_query,
            effective_query=qp.effective_query,
            search_query=qp.search_query,
            strategy=qp.strategy,
            rewrite_latency_ms=qp.rewrite_latency_ms,
            degraded=qp.degraded,
            degraded_reason=qp.degraded_reason,
            synonym_applied=qp.synonym_applied,
            synonym_expansions=qp.synonym_expansions,
        )

    def _resolve_rewrite_enabled(self, req: RetrieveRequest) -> bool:
        # 请求级优先于全局 QUERY_REWRITE_ENABLED。
        if req.query_options and req.query_options.enabled is not None:
            return req.query_options.enabled
        return settings.query_rewrite_enabled

    async def _retrieve_vector_only(
        self, req: RetrieveRequest, tenant_id: str, top_k: int, search_query: str,
        *, kb_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], HybridRetrievalMetadata]:
        effective_kb_id = kb_id if kb_id is not None else req.kb_id
        query_vector = await self._embedding.embed_query(search_query)
        hits = await self._vector_store.similarity_search(
            query_vector,
            tenant_id=tenant_id,
            kb_id=effective_kb_id,
            top_k=top_k,
        )
        logger.info("VECTOR_SEARCH_SUCCESS | kb_id=%s | count=%d", effective_kb_id, len(hits))

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
        self, req: RetrieveRequest, tenant_id: str, top_k: int, search_query: str,
        *, kb_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], HybridRetrievalMetadata]:
        if self._keyword_search is None:
            raise KeywordSearchError("keyword search provider not configured")

        effective_kb_id = kb_id if kb_id is not None else req.kb_id
        hits = await self._keyword_search.keyword_search(
            query=search_query,
            tenant_id=tenant_id,
            kb_id=effective_kb_id,
            top_k=top_k,
        )
        logger.info("BM25_SEARCH_SUCCESS | kb_id=%s | count=%d", effective_kb_id, len(hits))

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
        self, req: RetrieveRequest, tenant_id: str, search_query: str,
        *, kb_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], HybridRetrievalMetadata]:
        if self._keyword_search is None:
            raise KeywordSearchError("keyword search provider not configured for hybrid mode")

        effective_kb_id = kb_id if kb_id is not None else req.kb_id

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

        # 并行执行向量召回和 BM25 召回（统一使用 search_query）
        query_vector = await self._embedding.embed_query(search_query)
        vector_task = self._vector_store.similarity_search(
            query_vector, tenant_id=tenant_id, kb_id=effective_kb_id, top_k=vector_top_k
        )
        bm25_task = self._keyword_search.keyword_search(
            query=search_query, tenant_id=tenant_id, kb_id=effective_kb_id, top_k=bm25_top_k
        )

        vector_hits, bm25_hits = None, None
        bm25_failed = False
        try:
            vector_hits, bm25_hits = await asyncio.gather(vector_task, bm25_task)
            logger.info(
                "VECTOR_SEARCH_SUCCESS | kb_id=%s | count=%d", effective_kb_id, len(vector_hits)
            )
            logger.info("BM25_SEARCH_SUCCESS | kb_id=%s | count=%d", effective_kb_id, len(bm25_hits))
        except KeywordSearchError as exc:
            # BM25 失败不影响主链路：记录日志并降级为纯向量结果。
            logger.error(
                "BM25_SEARCH_FAILED | kb_id=%s | user_id=%s | error=%s",
                effective_kb_id,
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
            logger.warning("HYBRID_SEARCH_DEGRADED | kb_id=%s | reason=bm25_failed", effective_kb_id)
        else:
            # 正常 RRF 融合
            fused = self._hybrid_search.fuse_rrf(
                vector_chunks=vector_hits,
                bm25_chunks=bm25_hits,
                top_n=settings.hybrid_top_n,
            )
            logger.info(
                "RRF_FUSION_SUCCESS | kb_id=%s | vector_count=%d | bm25_count=%d | fused_count=%d",
                effective_kb_id,
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
