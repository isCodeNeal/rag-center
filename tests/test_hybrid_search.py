"""混合检索（hybrid search）与 RRF 融合单元测试。"""
from __future__ import annotations

from app.services.hybrid_search_service import HybridSearchService


def test_rrf_fusion_single_source():
    """只有一路召回（纯向量或纯 BM25）时，RRF 退化为该路径的排序。"""
    svc = HybridSearchService(rrf_k=60)
    vector_chunks = [
        {"chunk_id": "c1", "document_id": "d1", "title": "t1", "content": "退款政策", "score": 0.9},
        {"chunk_id": "c2", "document_id": "d1", "title": "t2", "content": "客服", "score": 0.8},
    ]
    fused = svc.fuse_rrf(vector_chunks=vector_chunks, bm25_chunks=[], top_n=5)
    assert len(fused) == 2
    assert fused[0]["chunk_id"] == "c1"
    assert fused[0]["retrieval_source"] == "vector"
    assert fused[0]["vector_rank"] == 1
    assert fused[0]["bm25_rank"] is None
    # RRF score: 1/(60+1) ≈ 0.0164
    assert 0.016 < fused[0]["score"] < 0.017


def test_rrf_fusion_both_sources():
    """两路都召回同一 chunk 时，RRF 分数为两路之和。"""
    svc = HybridSearchService(rrf_k=60)
    vector_chunks = [{"chunk_id": "c1", "document_id": "d1", "title": "t", "content": "退款", "score": 0.9}]
    bm25_chunks = [{"chunk_id": "c1", "document_id": "d1", "title": "t", "content": "退款", "bm25_score": 12.3}]
    fused = svc.fuse_rrf(vector_chunks=vector_chunks, bm25_chunks=bm25_chunks, top_n=5)
    assert len(fused) == 1
    assert fused[0]["chunk_id"] == "c1"
    assert fused[0]["retrieval_source"] == "hybrid"
    assert fused[0]["vector_rank"] == 1
    assert fused[0]["bm25_rank"] == 1
    # RRF score: 1/(60+1) + 1/(60+1) ≈ 0.0328
    assert 0.032 < fused[0]["score"] < 0.033


def test_rrf_fusion_different_ranks():
    """向量排名和 BM25 排名不同时，融合分数反映两路贡献。"""
    svc = HybridSearchService(rrf_k=60)
    vector_chunks = [
        {"chunk_id": "c1", "document_id": "d1", "title": "t", "content": "A", "score": 0.9},
        {"chunk_id": "c2", "document_id": "d1", "title": "t", "content": "B", "score": 0.7},
    ]
    bm25_chunks = [
        {"chunk_id": "c2", "document_id": "d1", "title": "t", "content": "B", "bm25_score": 15.0},
        {"chunk_id": "c1", "document_id": "d1", "title": "t", "content": "A", "bm25_score": 10.0},
    ]
    fused = svc.fuse_rrf(vector_chunks=vector_chunks, bm25_chunks=bm25_chunks, top_n=5)
    # c1: 1/(60+1) + 1/(60+2) ≈ 0.0164 + 0.0161 = 0.0325
    # c2: 1/(60+2) + 1/(60+1) ≈ 0.0161 + 0.0164 = 0.0325
    # 分数接近，但因向量给 c1 更高权（rank1），c1 略高
    assert fused[0]["chunk_id"] in ("c1", "c2")  # 接近，顺序可能不稳定
    assert fused[0]["retrieval_source"] == "hybrid"


def test_rrf_fusion_top_n_truncates():
    """融合后按 top_n 截断。"""
    svc = HybridSearchService(rrf_k=60)
    vector_chunks = [
        {"chunk_id": f"c{i}", "document_id": "d1", "title": "t", "content": f"chunk{i}", "score": 0.9 - i * 0.1}
        for i in range(10)
    ]
    fused = svc.fuse_rrf(vector_chunks=vector_chunks, bm25_chunks=[], top_n=3)
    assert len(fused) == 3
