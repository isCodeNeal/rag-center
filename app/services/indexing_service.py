"""Indexing service。

负责同步的 split -> embed -> index 流水线。这是未来迁移到 BackgroundTasks /
Celery / 消息队列时唯一需要改动的接缝：只需要改 `index_document`，API 和其它
service 都不用变。

这里故意不管理事务/commit —— 调用方（DocumentService）拥有这个工作单元，由它
来原子地记录 SUCCESS/FAILED 状态。

【混合检索】：同时写入 pgvector 和 Elasticsearch；ES 写入失败不影响主链路，
但会记录日志。
"""
from __future__ import annotations

from app.core.exceptions import IndexingError
from app.core.logging import get_logger
from app.models.document import Document
from app.providers.embedding.base import EmbeddingProvider
from app.providers.keyword_search.base import KeywordSearchProvider
from app.providers.parsers.base import DocumentParser
from app.providers.vectorstores.base import VectorStore
from app.utils.id_generator import new_chunk_id
from app.utils.text_splitter import TextSplitter

logger = get_logger(__name__)


class IndexingService:
    def __init__(
        self,
        *,
        parser: DocumentParser,
        splitter: TextSplitter,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
        keyword_search_provider: KeywordSearchProvider | None = None,
    ):
        self._parser = parser
        self._splitter = splitter
        self._embedding = embedding_provider
        self._vector_store = vector_store
        self._keyword_search = keyword_search_provider

    async def index_document(self, document: Document, content: str) -> int:
        """Parse -> split -> embed -> 写入向量存储 + 关键词检索引擎。

        返回写入的 chunk 数量。任何失败都会抛出 IndexingError。
        """
        # 1. 解析为归一化后的纯文本
        text = self._parser.parse(content, source_type=document.source_type)

        # 2. 切分为多个 chunk
        pieces = self._splitter.split(text)
        if not pieces:
            raise IndexingError("document produced no chunks after splitting")

        # 3. 对所有 chunk 进行 embedding
        vectors = await self._embedding.embed_texts(pieces)

        # 4. 构建 chunk payload 并写入向量存储
        chunks = [
            {
                "id": new_chunk_id(),
                "tenant_id": document.tenant_id,
                "kb_id": document.kb_id,
                "document_id": document.id,
                "title": document.title,
                "content": piece,
                "metadata": {"seq": seq, "source_type": document.source_type},
                "embedding": vector,
            }
            for seq, (piece, vector) in enumerate(zip(pieces, vectors, strict=True))
        ]
        await self._vector_store.add_chunks(chunks)

        # 5. 同时写入关键词检索引擎（best-effort：失败不影响主链路，但记录日志）
        if self._keyword_search is not None:
            try:
                await self._keyword_search.add_chunks(chunks)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "KEYWORD_SEARCH_WRITE_FAILED | document_id=%s | count=%d | error=%s",
                    document.id,
                    len(chunks),
                    exc,
                )

        logger.info("indexed document_id=%s chunks=%d", document.id, len(chunks))
        return len(chunks)
