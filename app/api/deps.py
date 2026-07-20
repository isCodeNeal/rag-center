"""FastAPI 依赖装配。

按请求组装 repository、provider 与 service。Provider 从配置中选择（embedding
provider、向量库），因此业务代码不会直接选定具体的厂商/存储实现——这也是
以后替换具体实现的切入点。
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.providers.embedding.base import EmbeddingProvider
from app.providers.embedding.openai_compatible import OpenAICompatibleEmbeddingProvider
from app.providers.parsers.base import DocumentParser
from app.providers.parsers.text import TextDocumentParser
from app.providers.vectorstores.base import VectorStore
from app.providers.vectorstores.pgvector import VECTOR_STORE_NAME, PgVectorStore
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.repositories.retrieval_log_repository import RetrievalLogRepository
from app.services.document_service import DocumentService
from app.services.indexing_service import IndexingService
from app.services.knowledge_base_service import KnowledgeBaseService
from app.services.rag_service import RAGService
from app.utils.text_splitter import CharacterTextSplitter, TextSplitter


# ----- 数据库 session -----
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_session():
        yield session


# ----- Provider（从配置中选择）-----
def get_embedding_provider() -> EmbeddingProvider:
    # 第一阶段仅提供 OpenAI 兼容的 provider。
    return OpenAICompatibleEmbeddingProvider()


def get_document_parser() -> DocumentParser:
    return TextDocumentParser()


def get_text_splitter() -> TextSplitter:
    return CharacterTextSplitter()


def get_vector_store(db: AsyncSession = Depends(get_db)) -> VectorStore:
    if settings.vector_store == "pgvector":
        return PgVectorStore(ChunkRepository(db))
    # 后续可在此处扩展 milvus / qdrant / elastic 等选择逻辑。
    raise ValueError(f"unsupported VECTOR_STORE: {settings.vector_store}")


def get_vector_store_name() -> str:
    return VECTOR_STORE_NAME if settings.vector_store == "pgvector" else settings.vector_store


# ----- Service -----
def get_knowledge_base_service(
    db: AsyncSession = Depends(get_db),
) -> KnowledgeBaseService:
    return KnowledgeBaseService(db, KnowledgeBaseRepository(db))


def get_document_service(
    db: AsyncSession = Depends(get_db),
    embedding: EmbeddingProvider = Depends(get_embedding_provider),
    parser: DocumentParser = Depends(get_document_parser),
    splitter: TextSplitter = Depends(get_text_splitter),
    vector_store: VectorStore = Depends(get_vector_store),
) -> DocumentService:
    indexing = IndexingService(
        parser=parser,
        splitter=splitter,
        embedding_provider=embedding,
        vector_store=vector_store,
    )
    return DocumentService(
        db,
        kb_repository=KnowledgeBaseRepository(db),
        document_repository=DocumentRepository(db),
        indexing_service=indexing,
    )


def get_rag_service(
    db: AsyncSession = Depends(get_db),
    embedding: EmbeddingProvider = Depends(get_embedding_provider),
    vector_store: VectorStore = Depends(get_vector_store),
    vector_store_name: str = Depends(get_vector_store_name),
) -> RAGService:
    return RAGService(
        db,
        kb_repository=KnowledgeBaseRepository(db),
        retrieval_log_repository=RetrievalLogRepository(db),
        embedding_provider=embedding,
        vector_store=vector_store,
        vector_store_name=vector_store_name,
    )
