"""Indexing service.

Owns the synchronous split -> embed -> index pipeline. This is the single seam that
later migrates to BackgroundTasks / Celery / a queue: only `index_document` changes,
not the API or the rest of the services.

It intentionally does NOT manage transactions/commits — the caller (DocumentService)
owns the unit of work so it can record SUCCESS/FAILED status atomically.
"""
from __future__ import annotations

from app.core.exceptions import IndexingError
from app.core.logging import get_logger
from app.models.document import Document
from app.providers.embedding.base import EmbeddingProvider
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
    ):
        self._parser = parser
        self._splitter = splitter
        self._embedding = embedding_provider
        self._vector_store = vector_store

    async def index_document(self, document: Document, content: str) -> int:
        """Parse -> split -> embed -> write to the vector store.

        Returns the number of chunks written. Raises IndexingError on any failure.
        """
        # 1. Parse to normalized plain text.
        text = self._parser.parse(content, source_type=document.source_type)

        # 2. Split into chunks.
        pieces = self._splitter.split(text)
        if not pieces:
            raise IndexingError("document produced no chunks after splitting")

        # 3. Embed all chunks.
        vectors = await self._embedding.embed_texts(pieces)

        # 4. Build chunk payloads and write to the vector store.
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

        logger.info(
            "indexed document_id=%s chunks=%d", document.id, len(chunks)
        )
        return len(chunks)
