"""Document service —— 负责编排上传 + 同步索引流程。

事务/状态的归属在这里：先把 document 行落库（状态为 PROCESSING），再执行索引。
索引成功后状态改为 SUCCESS；任何失败都会先回滚 chunk、把 document 标记为
FAILED，然后再让异常继续往外抛。
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizError, IndexingError, KnowledgeBaseNotFound
from app.core.logging import get_logger
from app.models.document import Document
from app.models.enums import DocumentStatus
from app.repositories.document_repository import DocumentRepository
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.schemas.document import UploadDocumentData, UploadDocumentRequest
from app.services.indexing_service import IndexingService
from app.utils.id_generator import new_document_id

logger = get_logger(__name__)


class DocumentService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        kb_repository: KnowledgeBaseRepository,
        document_repository: DocumentRepository,
        indexing_service: IndexingService,
    ):
        self._session = session
        self._kb_repo = kb_repository
        self._doc_repo = document_repository
        self._indexing = indexing_service

    async def upload(self, req: UploadDocumentRequest) -> UploadDocumentData:
        # 校验该租户下知识库是否存在
        kb = await self._kb_repo.get_for_tenant(req.kb_id, req.tenant_id)
        if kb is None:
            raise KnowledgeBaseNotFound(req.kb_id)

        # 1. 创建 document（状态 PROCESSING）并提前落库
        document = Document(
            id=new_document_id(),
            tenant_id=req.tenant_id,
            kb_id=req.kb_id,
            title=req.title,
            source_type=req.source_type or "text",
            status=DocumentStatus.PROCESSING.value,
        )
        await self._doc_repo.create(document)
        await self._session.commit()

        # 2. 同步执行 split + embed + index
        try:
            chunk_count = await self._indexing.index_document(document, req.content)
            document.status = DocumentStatus.SUCCESS.value
            await self._session.commit()
            logger.info(
                "DOC_INDEXED | document_id=%s | kb_id=%s | chunks=%d",
                document.id,
                document.kb_id,
                chunk_count,
            )
        except Exception as exc:  # noqa: BLE001 - 标记为 FAILED，再转换为业务异常重新抛出
            await self._session.rollback()
            await self._mark_failed(document.id)
            logger.error("indexing failed for document_id=%s: %s", document.id, exc)
            if isinstance(exc, BizError):
                raise
            raise IndexingError(f"failed to index document: {exc}")

        return UploadDocumentData(
            document_id=document.id,
            kb_id=document.kb_id,
            status=DocumentStatus.SUCCESS.value,
            chunk_count=chunk_count,
        )

    async def _mark_failed(self, document_id: str) -> None:
        doc = await self._doc_repo.get(document_id)
        if doc is not None:
            doc.status = DocumentStatus.FAILED.value
            await self._session.commit()
