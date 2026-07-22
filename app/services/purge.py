"""双存储清理工具：删除某文档在 pgvector 和 ES 中的全部 chunk。

删文档、删库、reindex 三处都要清理旧 chunk，抽取统一函数避免重复。
ES 清理为 best-effort：失败只记日志，不阻断主流程（DB 记录仍会被删），
但会尽量清干净，避免检索命中脏数据。
"""
from __future__ import annotations

from app.core.logging import get_logger
from app.providers.keyword_search.base import KeywordSearchProvider
from app.repositories.chunk_repository import ChunkRepository

logger = get_logger(__name__)


async def purge_document_chunks(
    document_id: str,
    *,
    chunk_repository: ChunkRepository,
    keyword_search: KeywordSearchProvider | None,
) -> None:
    # 1. 清 pgvector
    await chunk_repository.delete_by_document_id(document_id)
    # 2. 清 ES（best-effort）
    if keyword_search is not None:
        try:
            await keyword_search.delete_by_document_id(document_id)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "PURGE_ES_FAILED | document_id=%s | error=%s", document_id, exc
            )
