"""KeywordSearchProvider 抽象接口。

第一版提供 ElasticsearchKeywordSearchProvider（BM25）,后续可扩展 OpenSearchKeywordSearchProvider。
流经 `add_chunks` 的 chunk dict 应包含以下字段（与 VectorStore 一致）：
    id, tenant_id, kb_id, document_id, title, content, metadata

注意：**不要**把 embedding 向量写入 Elasticsearch。

`keyword_search` 返回的 dict 包含：
    document_id, chunk_id, title, content, bm25_score
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class KeywordSearchProvider(ABC):
    @abstractmethod
    async def add_chunks(self, chunks: list[dict[str, Any]]) -> None:
        """将 chunk 文本写入关键词检索引擎（Elasticsearch index）。

        与 VectorStore.add_chunks 契约一致，但不写 embedding。chunk 至少包含：
        id (chunk_id), tenant_id, kb_id, document_id, title, content, metadata。
        """
        raise NotImplementedError

    @abstractmethod
    async def keyword_search(
        self,
        *,
        query: str,
        tenant_id: str,
        kb_id: str,
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        """返回限定在 tenant_id + kb_id 范围内、BM25 相关性最高的 top_k 个 chunk。

        返回的 dict 至少包含：document_id, chunk_id, title, content, bm25_score。
        """
        raise NotImplementedError

    @abstractmethod
    async def delete_by_document_id(self, document_id: str) -> None:
        """删除某个文档下的所有 chunk（用于重新索引/清理场景）。"""
        raise NotImplementedError
