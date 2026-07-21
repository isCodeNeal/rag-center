"""混合检索 service：合并向量召回和 BM25 召回，并执行 RRF 融合排序。

RRF (Reciprocal Rank Fusion) 不依赖不同检索器的原始分数尺度，只看排名：

    rrf_score = 1 / (rrf_k + rank)

如果一个 chunk 同时被向量检索和 BM25 召回，则：

    fused_score = 1 / (rrf_k + vector_rank) + 1 / (rrf_k + bm25_rank)

融合后的 chunk dict 至少包含：
    document_id, chunk_id, title, content,
    score (融合分数 fused_score),
    vector_score, bm25_score, vector_rank, bm25_rank, retrieval_source
"""
from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class HybridSearchService:
    def __init__(self, *, rrf_k: int | None = None):
        self._rrf_k = rrf_k or settings.hybrid_rrf_k

    def fuse_rrf(
        self,
        *,
        vector_chunks: list[dict[str, Any]],
        bm25_chunks: list[dict[str, Any]],
        top_n: int,
    ) -> list[dict[str, Any]]:
        """RRF 融合向量召回和 BM25 召回的 chunk，返回按 fused_score 排序的 top_n 结果。

        输入：
        - vector_chunks: 向量召回结果，每个 dict 至少包含 chunk_id, document_id, title, content, score (向量分数)。
        - bm25_chunks: BM25 召回结果，每个 dict 至少包含 chunk_id, document_id, title, content, bm25_score。
        - top_n: 最终返回数量。

        输出：
        融合后的 chunk dict，新增字段：
        - score: 最终 RRF 融合分数 (fused_score)
        - vector_score / bm25_score: 原始检索分数，未召回的路径为 None
        - vector_rank / bm25_rank: 排名（从 1 开始），未召回的路径为 None
        - retrieval_source: "vector" / "bm25" / "hybrid"
        """
        # 构建排名映射：chunk_id -> (rank, original_dict)
        vector_rank_map: dict[str, tuple[int, dict]] = {
            c["chunk_id"]: (rank, c) for rank, c in enumerate(vector_chunks, start=1)
        }
        bm25_rank_map: dict[str, tuple[int, dict]] = {
            c["chunk_id"]: (rank, c) for rank, c in enumerate(bm25_chunks, start=1)
        }

        # 去重合并：按 chunk_id 合并两路结果
        all_chunk_ids = set(vector_rank_map.keys()) | set(bm25_rank_map.keys())
        fused = []
        for chunk_id in all_chunk_ids:
            vector_entry = vector_rank_map.get(chunk_id)
            bm25_entry = bm25_rank_map.get(chunk_id)

            # 基础字段从任一路径取（两路若都召回，取向量那路的 title/content/document_id，保证一致）
            base_chunk = vector_entry[1] if vector_entry else bm25_entry[1]  # type: ignore
            vector_rank, vector_score = (vector_entry[0], base_chunk["score"]) if vector_entry else (None, None)
            bm25_rank, bm25_score = (bm25_entry[0], bm25_entry[1]["bm25_score"]) if bm25_entry else (None, None)

            # RRF 分数：只对召回的路径计算 1/(rrf_k + rank)
            rrf_score = 0.0
            if vector_rank is not None:
                rrf_score += 1.0 / (self._rrf_k + vector_rank)
            if bm25_rank is not None:
                rrf_score += 1.0 / (self._rrf_k + bm25_rank)

            # 来源标记
            if vector_rank is not None and bm25_rank is not None:
                source = "hybrid"
            elif vector_rank is not None:
                source = "vector"
            else:
                source = "bm25"

            fused.append({
                "document_id": base_chunk["document_id"],
                "chunk_id": chunk_id,
                "title": base_chunk["title"],
                "content": base_chunk["content"],
                "score": rrf_score,
                "vector_score": vector_score,
                "bm25_score": bm25_score,
                "vector_rank": vector_rank,
                "bm25_rank": bm25_rank,
                "retrieval_source": source,
            })

        # 按 RRF 融合分数降序排序，截断到 top_n
        fused.sort(key=lambda c: c["score"], reverse=True)
        return fused[:top_n]
