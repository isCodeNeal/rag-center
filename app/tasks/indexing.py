"""Celery 索引任务：后台异步执行文档索引。

设计要点：
- Task 使用**独立的 DB session**（SessionLocal），不复用 FastAPI 请求 session。
- IndexingService/DocumentService 全是 async，Celery worker 是同步上下文，因此
  用 asyncio.run 包一层来驱动 async 索引逻辑（每个任务一个事件循环，简单可靠；
  rag-center 一份文档一个任务，不存在需要复用事件循环的高频场景）。
- 可重试错误（Embedding 超时、向量库/网络抖动）调用 self.retry() 重投；
  其它错误由 index_existing_document 内部落 status=FAILED 并记录 error_message。
"""
from __future__ import annotations

import asyncio

from app.celery_app import celery_app
from app.core.exceptions import EmbeddingError, VectorStoreError
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.providers.embedding.openai_compatible import OpenAICompatibleEmbeddingProvider
from app.providers.keyword_search.elasticsearch import (
    KEYWORD_SEARCH_PROVIDER_NAME,
    ElasticsearchKeywordSearchProvider,
)
from app.providers.parsers.text import TextDocumentParser
from app.providers.vectorstores.pgvector import PgVectorStore
from app.core.config import settings
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.services.document_service import DocumentService
from app.services.indexing_service import IndexingService
from app.utils.text_splitter import CharacterTextSplitter

logger = get_logger(__name__)

# 可重试的错误类型：外部依赖抖动/超时，重试有意义。
_RETRYABLE = (EmbeddingError, VectorStoreError, ConnectionError, TimeoutError)


async def _run_index(document_id: str) -> int:
    """用独立 session 组装依赖并执行索引。"""
    async with SessionLocal() as session:
        keyword_search = (
            ElasticsearchKeywordSearchProvider()
            if settings.keyword_search_provider == KEYWORD_SEARCH_PROVIDER_NAME
            else None
        )
        indexing = IndexingService(
            parser=TextDocumentParser(),
            splitter=CharacterTextSplitter(),
            embedding_provider=OpenAICompatibleEmbeddingProvider(),
            vector_store=PgVectorStore(ChunkRepository(session)),
            keyword_search_provider=keyword_search,
        )
        service = DocumentService(
            session,
            kb_repository=KnowledgeBaseRepository(session),
            document_repository=DocumentRepository(session),
            chunk_repository=ChunkRepository(session),
            indexing_service=indexing,
            keyword_search=keyword_search,
        )
        return await service.index_existing_document(document_id)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=10)
def index_document_task(self, document_id: str):
    """索引单个文档。document 必须已存在且 status=PROCESSING。"""
    logger.info("INDEX_TASK_START | document_id=%s | attempt=%d", document_id, self.request.retries)
    try:
        chunk_count = asyncio.run(_run_index(document_id))
        logger.info(
            "INDEX_TASK_DONE | document_id=%s | chunks=%d", document_id, chunk_count
        )
        return {"document_id": document_id, "chunk_count": chunk_count}
    except _RETRYABLE as exc:
        # 可恢复错误：重投。注意 index_existing_document 已把 status 落为 FAILED，
        # retry 前重置回 PROCESSING，让下次执行不被 "非 PROCESSING 直接 return" 拦截。
        logger.warning(
            "INDEX_TASK_RETRY | document_id=%s | attempt=%d | error=%s",
            document_id,
            self.request.retries,
            exc,
        )
        asyncio.run(_reset_to_processing(document_id))
        raise self.retry(exc=exc)
    except Exception as exc:  # noqa: BLE001
        # 不可恢复错误：status 已由 index_existing_document 落为 FAILED，记日志即可。
        logger.error("INDEX_TASK_FAILED | document_id=%s | error=%s", document_id, exc)
        return {"document_id": document_id, "error": str(exc)[:200]}


async def _reset_to_processing(document_id: str) -> None:
    """retry 前把 status 重置回 PROCESSING，以便下次任务能真正执行索引。"""
    from app.models.enums import DocumentStatus

    async with SessionLocal() as session:
        repo = DocumentRepository(session)
        doc = await repo.get(document_id)
        if doc is not None:
            doc.status = DocumentStatus.PROCESSING.value
            doc.error_message = None
            await session.commit()
