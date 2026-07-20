"""VectorStore 抽象接口。

第一阶段提供 PgVectorStore 实现，但没有任何 service 直接依赖 pgvector —— 只依赖
这个接口。后续的存储（Milvus、Qdrant、Elastic）实现同一套契约即可接入。

流经 `add_chunks` 的 chunk dict 应包含以下字段：
    id, tenant_id, kb_id, document_id, title, content, metadata, embedding

`similarity_search` 返回的 dict 包含：
    document_id, chunk_id, title, content, score
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class VectorStore(ABC):
    @abstractmethod
    async def add_chunks(self, chunks: list[dict[str, Any]]) -> None:
        """将 chunk（含 embedding）持久化写入存储。"""
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
        """返回限定在 tenant_id + kb_id 范围内、最相似的 top_k 个 chunk。"""
        raise NotImplementedError

    @abstractmethod
    async def delete_by_document_id(self, document_id: str) -> None:
        """删除某个文档下的所有 chunk（用于重新索引/清理场景）。"""
        raise NotImplementedError
