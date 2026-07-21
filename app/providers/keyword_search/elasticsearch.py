"""基于 Elasticsearch 8.x 的 BM25 关键词检索实现。

写入 chunk 时会自动创建 index（若不存在），mapping 使用 IK 中文分词器（ik_max_word / ik_smart）。
BM25 查询使用 multi_match(title^2, content)，并过滤 tenant_id + kb_id。
"""
from __future__ import annotations

import time
from typing import Any

from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk

from app.core.config import settings
from app.core.exceptions import KeywordSearchError
from app.core.logging import get_logger
from app.providers.keyword_search.base import KeywordSearchProvider

logger = get_logger(__name__)

KEYWORD_SEARCH_PROVIDER_NAME = "elasticsearch"


class ElasticsearchKeywordSearchProvider(KeywordSearchProvider):
    def __init__(
        self,
        *,
        es_url: str | None = None,
        index_name: str | None = None,
        analyzer: str | None = None,
        search_analyzer: str | None = None,
    ):
        self._es_url = es_url or settings.elasticsearch_url
        self._index = index_name or settings.elasticsearch_index
        self._analyzer = analyzer or settings.elasticsearch_analyzer
        self._search_analyzer = search_analyzer or settings.elasticsearch_search_analyzer
        self._client: AsyncElasticsearch | None = None

    @property
    def name(self) -> str:
        return KEYWORD_SEARCH_PROVIDER_NAME

    async def _get_client(self) -> AsyncElasticsearch:
        if self._client is None:
            self._client = AsyncElasticsearch([self._es_url])
        return self._client

    async def _ensure_index_exists(self) -> None:
        """确保索引存在；若不存在则创建（带 IK 分词 mapping）。

        title/content 使用 ik_max_word（index）+ ik_smart（search）。
        若 IK 插件未安装，ES 会拒绝创建索引并抛错（这是预期的，不静默忽略）。
        """
        client = await self._get_client()
        if await client.indices.exists(index=self._index):
            return

        # index mapping：title boost 2x, content 原权重。
        mapping = {
            "mappings": {
                "properties": {
                    "tenant_id": {"type": "keyword"},
                    "kb_id": {"type": "keyword"},
                    "document_id": {"type": "keyword"},
                    "chunk_id": {"type": "keyword"},
                    "title": {"type": "text", "analyzer": self._analyzer, "search_analyzer": self._search_analyzer},
                    "content": {"type": "text", "analyzer": self._analyzer, "search_analyzer": self._search_analyzer},
                    "metadata": {"type": "object", "enabled": False},
                    "created_at": {"type": "date"},
                }
            }
        }
        try:
            await client.indices.create(index=self._index, body=mapping)
            logger.info("ES_INDEX_CREATED | index=%s | analyzer=%s", self._index, self._analyzer)
        except Exception as exc:  # noqa: BLE001
            # 创建失败（比如 IK 插件未装）直接抛错，不静默吞掉。
            logger.error("ES_INDEX_CREATE_FAILED | index=%s | error=%s", self._index, exc)
            raise KeywordSearchError(f"failed to create ES index {self._index}: {exc}")

    async def add_chunks(self, chunks: list[dict[str, Any]]) -> None:
        if not chunks:
            return
        await self._ensure_index_exists()
        client = await self._get_client()

        # 构造 bulk actions，不写 embedding。
        actions = [
            {
                "_index": self._index,
                "_id": chunk["id"],
                "_source": {
                    "tenant_id": chunk["tenant_id"],
                    "kb_id": chunk["kb_id"],
                    "document_id": chunk["document_id"],
                    "chunk_id": chunk["id"],
                    "title": chunk["title"],
                    "content": chunk["content"],
                    "metadata": chunk.get("metadata", {}),
                    "created_at": chunk.get("created_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
            }
            for chunk in chunks
        ]
        try:
            success, errors = await async_bulk(client, actions, raise_on_error=False)
            if errors:
                logger.warning("ES_BULK_PARTIAL_FAIL | success=%d | errors=%s", success, errors[:3])
        except Exception as exc:  # noqa: BLE001
            logger.error("ES_ADD_CHUNKS_FAILED | count=%d | error=%s", len(chunks), exc)
            raise KeywordSearchError(f"es bulk add_chunks failed: {exc}")

    async def keyword_search(
        self,
        *,
        query: str,
        tenant_id: str,
        kb_id: str,
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        client = await self._get_client()
        body = {
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"tenant_id": tenant_id}},
                        {"term": {"kb_id": kb_id}},
                    ],
                    "must": {
                        "multi_match": {
                            "query": query,
                            "fields": ["title^2", "content"],
                        }
                    },
                }
            },
            "size": top_k,
        }
        try:
            resp = await client.search(index=self._index, body=body)
            hits = resp["hits"]["hits"]
            results = []
            for hit in hits:
                source = hit["_source"]
                results.append({
                    "document_id": source["document_id"],
                    "chunk_id": source["chunk_id"],
                    "title": source["title"],
                    "content": source["content"],
                    "bm25_score": hit["_score"],
                })
            return results
        except Exception as exc:  # noqa: BLE001
            logger.error("ES_KEYWORD_SEARCH_FAILED | query=%s | kb_id=%s | error=%s", query[:50], kb_id, exc)
            raise KeywordSearchError(f"es keyword_search failed: {exc}")

    async def delete_by_document_id(self, document_id: str) -> None:
        client = await self._get_client()
        body = {"query": {"term": {"document_id": document_id}}}
        try:
            await client.delete_by_query(index=self._index, body=body)
        except Exception as exc:  # noqa: BLE001
            logger.error("ES_DELETE_FAILED | document_id=%s | error=%s", document_id, exc)
            raise KeywordSearchError(f"es delete_by_document_id failed: {exc}")
