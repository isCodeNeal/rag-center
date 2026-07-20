"""Rerank provider 单元测试。"""
from __future__ import annotations

import pytest

from app.core.exceptions import LLMProviderError, RerankError
from app.providers.llm.base import LLMProvider
from app.providers.rerank.llm import LLMRerankProvider
from app.providers.rerank.noop import NoopRerankProvider


class _FakeLLM(LLMProvider):
    def __init__(self, result: dict):
        self.result = result

    async def chat_json(self, *, system_prompt: str, user_payload: dict, temperature: float = 0.0, timeout_seconds: int | None = None) -> dict:
        return self.result


class _FailingLLM(LLMProvider):
    async def chat_json(self, *, system_prompt: str, user_payload: dict, temperature: float = 0.0, timeout_seconds: int | None = None) -> dict:
        raise LLMProviderError("boom")


_CANDIDATES = [
    {
        "document_id": "doc-1",
        "chunk_id": "chunk-1",
        "title": "退款政策",
        "content": "用户可在订单完成后 7 天内申请退款。",
        "score": 0.86,
    },
    {
        "document_id": "doc-1",
        "chunk_id": "chunk-2",
        "title": "退款政策",
        "content": "特殊商品不支持无理由退款。",
        "score": 0.73,
    },
]


@pytest.mark.asyncio
async def test_noop_rerank_keeps_order_and_sets_none_score():
    provider = NoopRerankProvider()
    out = await provider.rerank(query="退款需要几天内申请？", chunks=_CANDIDATES, top_n=1)
    assert len(out) == 1
    assert out[0]["chunk_id"] == "chunk-1"
    assert out[0]["rerank_score"] is None


@pytest.mark.asyncio
async def test_llm_rerank_sorts_by_rerank_score():
    provider = LLMRerankProvider(
        _FakeLLM(
            {
                "rankings": [
                    {"chunk_id": "chunk-2", "rerank_score": 0.95, "reason": "更相关"},
                    {"chunk_id": "chunk-1", "rerank_score": 0.32, "reason": "次相关"},
                ]
            }
        )
    )
    out = await provider.rerank(query="退款需要几天内申请？", chunks=_CANDIDATES, top_n=2)
    assert [c["chunk_id"] for c in out] == ["chunk-2", "chunk-1"]
    assert out[0]["score"] == 0.73
    assert out[0]["rerank_score"] == 0.95


@pytest.mark.asyncio
async def test_llm_rerank_missing_chunk_defaults_to_zero():
    provider = LLMRerankProvider(_FakeLLM({"rankings": [{"chunk_id": "chunk-1", "rerank_score": 0.5}]}))
    out = await provider.rerank(query="退款需要几天内申请？", chunks=_CANDIDATES, top_n=2)
    assert out[0]["chunk_id"] == "chunk-1"
    # chunk-2 漏打分 -> 默认 0
    assert any(c["chunk_id"] == "chunk-2" and c["rerank_score"] == 0.0 for c in out)


@pytest.mark.asyncio
async def test_llm_rerank_llm_failure_raises_rerank_error():
    provider = LLMRerankProvider(_FailingLLM())
    with pytest.raises(RerankError):
        await provider.rerank(query="退款需要几天内申请？", chunks=_CANDIDATES, top_n=2)
