"""不重排的占位 RerankProvider。

用于 RERANK_PROVIDER=noop（或全局/单次请求关闭 rerank）时的实现：不调用任何
大模型，直接按输入顺序（即向量分数排序）截断到 top_n，并把 rerank_score
置为 None，语义上等价于"未重排"。
"""
from __future__ import annotations

from typing import Any

from app.providers.rerank.base import RerankProvider

NOOP_PROVIDER_NAME = "noop"


class NoopRerankProvider(RerankProvider):
    @property
    def name(self) -> str:
        return NOOP_PROVIDER_NAME

    async def rerank(
        self,
        *,
        query: str,
        chunks: list[dict[str, Any]],
        top_n: int,
    ) -> list[dict[str, Any]]:
        result = []
        for chunk in chunks[:top_n]:
            item = dict(chunk)
            item.setdefault("rerank_score", None)
            result.append(item)
        return result
