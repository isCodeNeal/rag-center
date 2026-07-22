"""Batch reindex documents in a knowledge base.

Usage:
  # Reindex all SUCCESS/FAILED documents in a KB
  python scripts/reindex_knowledge_base.py --kb-id <kb_id>

  # Reindex specific documents
  python scripts/reindex_knowledge_base.py --kb-id <kb_id> --document-id <id1> --document-id <id2>

  # Override tenant (optional; derived from KB record if omitted)
  python scripts/reindex_knowledge_base.py --kb-id <kb_id> --tenant-id <tenant_id>
"""
from __future__ import annotations

import argparse
import asyncio
from typing import Optional

from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.document import Document
from app.models.enums import DocumentStatus
from app.models.knowledge_base import KnowledgeBase
from app.providers.keyword_search.elasticsearch import (
    KEYWORD_SEARCH_PROVIDER_NAME,
    ElasticsearchKeywordSearchProvider,
)
from app.repositories.chunk_repository import ChunkRepository
from app.services.purge import purge_document_chunks
from app.tasks.indexing import index_document_task


async def _main(
    kb_id: str,
    tenant_id: Optional[str],
    document_ids: Optional[list[str]],
) -> None:
    keyword_search = (
        ElasticsearchKeywordSearchProvider()
        if settings.keyword_search_provider == KEYWORD_SEARCH_PROVIDER_NAME
        else None
    )

    async with SessionLocal() as session:
        # 1. Confirm the KB exists; derive tenant_id if not provided
        kb_result = await session.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
        kb = kb_result.scalar_one_or_none()
        if kb is None:
            raise SystemExit(f"KnowledgeBase not found: {kb_id}")

        if tenant_id is None:
            tenant_id = kb.tenant_id

        chunk_repo = ChunkRepository(session)

        # 2. Fetch target documents
        if document_ids:
            stmt = select(Document).where(
                Document.id.in_(document_ids),
                Document.kb_id == kb_id,
            )
        else:
            stmt = select(Document).where(
                Document.kb_id == kb_id,
                Document.status.in_(
                    [DocumentStatus.SUCCESS.value, DocumentStatus.FAILED.value]
                ),
            )

        doc_result = await session.execute(stmt)
        documents = doc_result.scalars().all()

        success = 0
        failed = 0
        skipped = 0

        # 3. Process each document
        for doc in documents:
            print(f"Reindexing document {doc.id}: {doc.title}", end="", flush=True)
            try:
                # Skip documents currently being processed
                if doc.status == DocumentStatus.PROCESSING.value:
                    print(" [SKIPPED: PROCESSING]")
                    skipped += 1
                    continue

                # a. Purge existing chunks
                await purge_document_chunks(
                    doc.id,
                    chunk_repository=chunk_repo,
                    keyword_search=keyword_search,
                )

                # b. Reset document status
                doc.status = DocumentStatus.PROCESSING.value
                doc.error_message = None

                # c. Persist status change before dispatching task
                await session.commit()

                # d. Submit Celery task
                index_document_task.delay(doc.id)

                print(" [OK: task submitted]")
                success += 1

            except Exception as exc:  # noqa: BLE001
                print(f" [FAILED: {exc}]")
                failed += 1

    print(f"\nDone: success={success}  failed={failed}  skipped={skipped}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Batch reindex documents in a knowledge base"
    )
    parser.add_argument("--kb-id", required=True, help="Target knowledge base ID")
    parser.add_argument(
        "--tenant-id",
        default=None,
        help="Tenant ID (derived from KB record if omitted)",
    )
    parser.add_argument(
        "--document-id",
        action="append",
        dest="document_ids",
        metavar="DOCUMENT_ID",
        help="Document ID to reindex (repeatable); if omitted, all SUCCESS/FAILED docs are reindexed",
    )
    args = parser.parse_args()
    asyncio.run(_main(args.kb_id, args.tenant_id, args.document_ids))
