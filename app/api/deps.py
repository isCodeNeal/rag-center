"""FastAPI 依赖装配。

按请求组装 repository、provider 与 service。Provider 从配置中选择（embedding
provider、向量库、LLM provider、rerank provider），因此业务代码不会直接选定
具体的厂商/存储实现——这也是以后替换具体实现的切入点。
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.providers.embedding.base import EmbeddingProvider
from app.providers.embedding.openai_compatible import OpenAICompatibleEmbeddingProvider
from app.providers.llm.base import LLMProvider
from app.providers.llm.openai_compatible import OpenAICompatibleLLMProvider
from app.providers.parsers.base import DocumentParser
from app.providers.parsers.text import TextDocumentParser
from app.providers.rerank.base import RerankProvider
from app.providers.rerank.llm import LLM_RERANK_PROVIDER_NAME, LLMRerankProvider
from app.providers.rerank.noop import NOOP_PROVIDER_NAME, NoopRerankProvider
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


def get_llm_provider() -> LLMProvider:
    # 第一阶段仅支持 openai_compatible；DeepSeek、百炼等兼容 OpenAI 协议的厂商
    # 都走这个实现，只需切换 LLM_BASE_URL / LLM_MODEL 配置。
    if settings.llm_provider == "openai_compatible":
        return OpenAICompatibleLLMProvider()
    raise ValueError(f"unsupported LLM_PROVIDER: {settings.llm_provider}")


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


def get_rerank_provider(
    llm_provider: LLMProvider = Depends(get_llm_provider),
) -> RerankProvider:
    # 第一版支持 llm（通过 LLMProvider 调大模型打分）和 noop（不重排）。
    if settings.rerank_provider == LLM_RERANK_PROVIDER_NAME:
        return LLMRerankProvider(llm_provider)
    if settings.rerank_provider == NOOP_PROVIDER_NAME:
        return NoopRerankProvider()
    raise ValueError(f"unsupported RERANK_PROVIDER: {settings.rerank_provider}")


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
    rerank_provider: RerankProvider = Depends(get_rerank_provider),
) -> RAGService:
    return RAGService(
        db,
        kb_repository=KnowledgeBaseRepository(db),
        retrieval_log_repository=RetrievalLogRepository(db),
        embedding_provider=embedding,
        vector_store=vector_store,
        vector_store_name=vector_store_name,
        rerank_provider=rerank_provider,
    )
