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
        self,
        req: UploadDocumentRequest | None,
        tenant_id: str,
        *,
        # multipart 模式时传入
        file_path: str | None = None,
        source_filename: str | None = None,
        source_type_override: str | None = None,
        title_override: str | None = None,
        kb_id_override: str | None = None,
    ) -> Document:
        """校验 kb 归属，建 PROCESSING 记录，commit 后返回。

        - JSON 模式：req 非 None，写入 content；file_path 等关键字参数均为 None。
        - multipart 模式：req 为 None，由关键字参数提供 kb_id / title / file_path 等；
          content 留空，由 Worker 的 index_existing_document 解析原文后填入。
        """
        # 统一取 kb_id
        resolved_kb_id: str = kb_id_override if kb_id_override is not None else (req.kb_id if req else "")
        kb = await self._kb_repo.get_for_tenant(resolved_kb_id, tenant_id)
        if kb is None:
            raise KnowledgeBaseNotFound(resolved_kb_id)

        if req is not None:
            # JSON 模式
            document = Document(
                id=new_document_id(),
                tenant_id=tenant_id,
                kb_id=req.kb_id,
                title=req.title,
                source_type=req.source_type or "text",
                status=DocumentStatus.PROCESSING.value,
                content=req.content or "",
                source_file_path=None,
                source_filename=None,
            )
        else:
            # multipart 模式：content 留空，等 Worker 解析原文后填入
            document = Document(
                id=new_document_id(),
                tenant_id=tenant_id,
                kb_id=resolved_kb_id,
                title=title_override or source_filename or "",
                source_type=source_type_override or "text",
                status=DocumentStatus.PROCESSING.value,
                content="",
                source_file_path=file_path,
                source_filename=source_filename,
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

        若 document.source_file_path 存在（multipart upload），先调用
        prepare_document_content 解析原文件，将结果写入 content 后再索引。

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
            # 如果有原文件路径（multipart upload / reparse），先解析原文件
            if document.source_file_path:
                try:
                    from app.services.document_ingestion import prepare_document_content  # noqa: PLC0415
                    parsed = await prepare_document_content(
                        content=None,
                        file_path=document.source_file_path,
                        filename=document.source_filename or document.title,
                    )
                    document.content = parsed.content
                    document.source_type = parsed.source_type
                    await self._session.commit()
                    logger.info(
                        "DOC_FILE_PARSED | document_id=%s | source_type=%s",
                        document_id,
                        parsed.source_type,
                    )
                except ImportError:
                    # TODO: Agent1 负责实现 document_ingestion 模块；运行时会存在
                    logger.warning(
                        "DOC_INGESTION_NOT_AVAILABLE | document_id=%s | skipping parse",
                        document_id,
                    )

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
            source_filename=document.source_filename,
            source_type=document.source_type,
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
    async def reindex(
        self, document_id: str, tenant_id: str, *, reparse: bool = False
    ) -> DocumentStatusData:
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
        # reparse=True 且有原文件路径时，清空 content 让 index_existing_document 重新解析
        if reparse and document.source_file_path:
            document.content = ""
            logger.info("DOC_REPARSE_SCHEDULED | document_id=%s", document_id)
        document.status = DocumentStatus.PROCESSING.value
        document.error_message = None
        await self._session.commit()
        # commit 后 server_onupdate 会刷新 updated_at，需 refresh 避免 async 下懒加载报错
        await self._session.refresh(document)
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
            source_filename=document.source_filename,
            source_type=document.source_type,
        )

    async def _mark_failed(self, document_id: str, error_message: str) -> None:
        doc = await self._doc_repo.get(document_id)
        if doc is not None:
            doc.status = DocumentStatus.FAILED.value
            doc.error_message = error_message[:2000]
            await self._session.commit()
