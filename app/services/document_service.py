"""Document service —— 文档生命周期编排。

索引改为 Celery 异步执行后，本 service 拆成两类职责：
- 建记录（upload API 用）：create_document_record —— 校验 kb 归属、建 PROCESSING
  记录并写入原文 content，commit 后立即返回，真正索引交给 Worker。
- 执行索引（Celery Task / reindex 用）：index_existing_document —— 从 DB 读原文，
  执行分块/embed/双写，落 SUCCESS 或 FAILED。
- 运维：get_status / delete_document / reindex。

删文档 / reindex 前用 purge_document_chunks 清理双存储旧 chunk。
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_codes import ErrorCode
from app.core.exceptions import (
    DocumentNotFound,
    KnowledgeBaseNotFound,
    raise_error,
)
from app.core.logging import get_logger
from app.models.document import Document
from app.models.enums import DocumentStatus
from app.providers.keyword_search.base import KeywordSearchProvider
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.schemas.document import (
    DocumentStatusData,
    UploadDocumentData,
    UploadDocumentRequest,
)
from app.services.indexing_service import IndexingService
from app.services.purge import purge_document_chunks
from app.utils.id_generator import new_document_id

logger = get_logger(__name__)


class DocumentService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        kb_repository: KnowledgeBaseRepository,
        document_repository: DocumentRepository,
        chunk_repository: ChunkRepository,
        indexing_service: IndexingService,
        keyword_search: KeywordSearchProvider | None = None,
    ):
        self._session = session
        self._kb_repo = kb_repository
        self._doc_repo = document_repository
        self._chunk_repo = chunk_repository
        self._indexing = indexing_service
        self._keyword_search = keyword_search

    # ----- 建记录（upload API）-----
    async def create_document_record(
        self, req: UploadDocumentRequest, tenant_id: str
    ) -> Document:
        """校验 kb 归属，建 PROCESSING 记录并写入原文 content，commit 后返回。"""
        kb = await self._kb_repo.get_for_tenant(req.kb_id, tenant_id)
        if kb is None:
            raise KnowledgeBaseNotFound(req.kb_id)

        document = Document(
            id=new_document_id(),
            tenant_id=tenant_id,
            kb_id=req.kb_id,
            title=req.title,
            source_type=req.source_type or "text",
            status=DocumentStatus.PROCESSING.value,
            content=req.content,
        )
        await self._doc_repo.create(document)
        await self._session.commit()
        logger.info(
            "DOC_RECORD_CREATED | document_id=%s | kb_id=%s", document.id, document.kb_id
        )
        return document

    # ----- 执行索引（Celery Task / reindex）-----
    async def index_existing_document(self, document_id: str) -> int:
        """读 document 原文，执行索引，更新 SUCCESS 或 FAILED。返回 chunk 数。

        status 不是 PROCESSING 时直接 return 0，防止重复执行。
        """
        document = await self._doc_repo.get(document_id)
        if document is None:
            logger.warning("INDEX_SKIP_NOT_FOUND | document_id=%s", document_id)
            return 0
        if document.status != DocumentStatus.PROCESSING.value:
            logger.info(
                "INDEX_SKIP_NOT_PROCESSING | document_id=%s | status=%s",
                document_id,
                document.status,
            )
            return 0

        try:
            chunk_count = await self._indexing.index_document(document, document.content)
            document.status = DocumentStatus.SUCCESS.value
            document.error_message = None
            await self._session.commit()
            logger.info(
                "DOC_INDEXED | document_id=%s | kb_id=%s | chunks=%d",
                document.id,
                document.kb_id,
                chunk_count,
            )
            return chunk_count
        except Exception as exc:  # noqa: BLE001
            await self._session.rollback()
            await self._mark_failed(document_id, str(exc))
            logger.error("INDEX_FAILED | document_id=%s | error=%s", document_id, exc)
            raise

    # ----- 状态查询 -----
    async def get_status(self, document_id: str, tenant_id: str) -> DocumentStatusData:
        document = await self._doc_repo.get_for_tenant(document_id, tenant_id)
        if document is None:
            raise DocumentNotFound(document_id)
        counts = await self._chunk_repo.count_by_document_ids([document.id])
        return DocumentStatusData(
            document_id=document.id,
            kb_id=document.kb_id,
            title=document.title,
            status=document.status,
            error_message=document.error_message,
            chunk_count=counts.get(document.id, 0),
            created_at=document.created_at,
            updated_at=document.updated_at,
        )

    # ----- 删除 -----
    async def delete_document(self, document_id: str, tenant_id: str) -> None:
        document = await self._doc_repo.get_for_tenant(document_id, tenant_id)
        if document is None:
            raise DocumentNotFound(document_id)
        if document.status == DocumentStatus.PROCESSING.value:
            raise_error(
                ErrorCode.PARAM_ERROR,
                msg="文档正在索引中，暂不能删除",
                detail=f"document_id={document_id} is PROCESSING",
            )
        await purge_document_chunks(
            document.id,
            chunk_repository=self._chunk_repo,
            keyword_search=self._keyword_search,
        )
        await self._doc_repo.delete(document)
        await self._session.commit()
        logger.info("DOC_DELETED | document_id=%s", document_id)

    # ----- 重试索引 -----
    async def reindex(self, document_id: str, tenant_id: str) -> DocumentStatusData:
        document = await self._doc_repo.get_for_tenant(document_id, tenant_id)
        if document is None:
            raise DocumentNotFound(document_id)
        if document.status == DocumentStatus.PROCESSING.value:
            raise_error(
                ErrorCode.PARAM_ERROR,
                msg="文档正在索引中，请稍后再试",
                detail=f"document_id={document_id} status={document.status}",
            )
        # 清理可能存在的残留 chunk
        await purge_document_chunks(
            document.id,
            chunk_repository=self._chunk_repo,
            keyword_search=self._keyword_search,
        )
        document.status = DocumentStatus.PROCESSING.value
        document.error_message = None
        await self._session.commit()
        counts = await self._chunk_repo.count_by_document_ids([document.id])
        return DocumentStatusData(
            document_id=document.id,
            kb_id=document.kb_id,
            title=document.title,
            status=document.status,
            error_message=document.error_message,
            chunk_count=counts.get(document.id, 0),
            created_at=document.created_at,
            updated_at=document.updated_at,
        )

    async def _mark_failed(self, document_id: str, error_message: str) -> None:
        doc = await self._doc_repo.get(document_id)
        if doc is not None:
            doc.status = DocumentStatus.FAILED.value
            doc.error_message = error_message[:2000]
            await self._session.commit()
