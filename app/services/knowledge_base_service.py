"""知识库 service。"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_codes import ErrorCode
from app.core.exceptions import KnowledgeBaseNotFound, raise_error
from app.core.logging import get_logger
from app.models.enums import DocumentStatus
from app.models.knowledge_base import KnowledgeBase
from app.providers.keyword_search.base import KeywordSearchProvider
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.schemas.knowledge_base import (
    CreateKnowledgeBaseRequest,
    KnowledgeBaseData,
    KnowledgeBaseDetailData,
    KnowledgeTreeDoc,
    KnowledgeTreeKb,
    KnowledgeTreeTenant,
    UpdateKnowledgeBaseRequest,
)
from app.services.purge import purge_document_chunks
from app.utils.id_generator import new_kb_id

logger = get_logger(__name__)


def _validate_settings(settings: dict) -> None:
    """校验 settings.synonyms 结构：每组须有非空 terms 和 expand 数组。"""
    synonyms = settings.get("synonyms")
    if synonyms is None:
        return
    if not isinstance(synonyms, list):
        raise_error(ErrorCode.PARAM_ERROR, msg="settings.synonyms 必须是数组")
    for i, group in enumerate(synonyms):
        if not isinstance(group, dict):
            raise_error(ErrorCode.PARAM_ERROR, msg=f"synonyms[{i}] 必须是对象")
        terms = group.get("terms")
        expand = group.get("expand")
        if not isinstance(terms, list) or not terms:
            raise_error(ErrorCode.PARAM_ERROR, msg=f"synonyms[{i}].terms 必须是非空数组")
        if not isinstance(expand, list) or not expand:
            raise_error(ErrorCode.PARAM_ERROR, msg=f"synonyms[{i}].expand 必须是非空数组")


class KnowledgeBaseService:
    def __init__(
        self,
        session: AsyncSession,
        kb_repository: KnowledgeBaseRepository,
        document_repository: DocumentRepository | None = None,
        chunk_repository: ChunkRepository | None = None,
        keyword_search: KeywordSearchProvider | None = None,
    ):
        self._session = session
        self._kb_repo = kb_repository
        self._doc_repo = document_repository
        self._chunk_repo = chunk_repository
        self._keyword_search = keyword_search

    async def create(self, req: CreateKnowledgeBaseRequest, tenant_id: str) -> KnowledgeBaseData:
        kb = KnowledgeBase(
            id=new_kb_id(),
            tenant_id=tenant_id,
            name=req.name,
            description=req.description,
            settings={},
        )
        await self._kb_repo.create(kb)
        await self._session.commit()
        await self._session.refresh(kb)
        logger.info("KB_CREATED | kb_id=%s | tenant_id=%s | name=%s", kb.id, kb.tenant_id, kb.name)
        return KnowledgeBaseData(
            kb_id=kb.id,
            name=kb.name,
            tenant_id=kb.tenant_id,
            created_at=kb.created_at,
        )

    async def get_tree(
        self, tenant_id: str, keyword: str | None = None
    ) -> list[KnowledgeTreeTenant]:
        kbs = await self._kb_repo.list_by_tenant(tenant_id, keyword)
        kb_ids = [kb.id for kb in kbs]
        # 三种状态都返回，让失败/处理中的文档在列表里可见。
        docs = await self._doc_repo.list_by_kb_ids(kb_ids) if kb_ids else []
        doc_ids = [d.id for d in docs]
        counts = await self._chunk_repo.count_by_document_ids(doc_ids) if doc_ids else {}

        docs_by_kb: dict[str, list[KnowledgeTreeDoc]] = {}
        for d in docs:
            docs_by_kb.setdefault(d.kb_id, []).append(
                KnowledgeTreeDoc(
                    document_id=d.id,
                    title=d.title,
                    status=d.status,
                    chunk_count=counts.get(d.id, 0),
                    created_at=d.created_at,
                    error_message=d.error_message,
                )
            )

        if not kbs:
            return []
        tenant = KnowledgeTreeTenant(tenant_id=tenant_id, knowledge_bases=[])
        for kb in kbs:
            tenant.knowledge_bases.append(
                KnowledgeTreeKb(
                    kb_id=kb.id,
                    name=kb.name,
                    description=kb.description,
                    created_at=kb.created_at,
                    documents=docs_by_kb.get(kb.id, []),
                )
            )
        return [tenant]

    async def get_detail(self, kb_id: str, tenant_id: str) -> KnowledgeBaseDetailData:
        kb = await self._kb_repo.get_for_tenant(kb_id, tenant_id)
        if kb is None:
            raise KnowledgeBaseNotFound(kb_id)
        docs = await self._doc_repo.list_by_kb(kb_id)
        return KnowledgeBaseDetailData(
            kb_id=kb.id,
            name=kb.name,
            description=kb.description,
            settings=kb.settings or {},
            document_count=len(docs),
            created_at=kb.created_at,
            updated_at=kb.updated_at,
        )

    async def update(
        self, kb_id: str, tenant_id: str, req: UpdateKnowledgeBaseRequest
    ) -> KnowledgeBaseDetailData:
        if req.name is None and req.description is None and req.settings is None:
            raise_error(ErrorCode.PARAM_ERROR, msg="name/description/settings 至少传一个")
        kb = await self._kb_repo.get_for_tenant(kb_id, tenant_id)
        if kb is None:
            raise KnowledgeBaseNotFound(kb_id)

        if req.name is not None:
            kb.name = req.name
        if req.description is not None:
            kb.description = req.description
        if req.settings is not None:
            _validate_settings(req.settings)
            kb.settings = req.settings  # 整段替换
        await self._session.commit()
        await self._session.refresh(kb)
        logger.info("KB_UPDATED | kb_id=%s", kb.id)
        docs = await self._doc_repo.list_by_kb(kb_id)
        return KnowledgeBaseDetailData(
            kb_id=kb.id,
            name=kb.name,
            description=kb.description,
            settings=kb.settings or {},
            document_count=len(docs),
            created_at=kb.created_at,
            updated_at=kb.updated_at,
        )

    async def delete(self, kb_id: str, tenant_id: str) -> None:
        kb = await self._kb_repo.get_for_tenant(kb_id, tenant_id)
        if kb is None:
            raise KnowledgeBaseNotFound(kb_id)
        docs = await self._doc_repo.list_by_kb(kb_id)
        # 库下还有 PROCESSING 文档时拒绝删除，Worker 可能还在跑。
        if any(d.status == DocumentStatus.PROCESSING.value for d in docs):
            raise_error(
                ErrorCode.PARAM_ERROR,
                msg="知识库下有文档正在索引中，暂不能删除",
                detail=f"kb_id={kb_id} has PROCESSING documents",
            )
        # 严格顺序：逐文档清双存储 -> 删 documents -> 删 kb。
        for d in docs:
            await purge_document_chunks(
                d.id,
                chunk_repository=self._chunk_repo,
                keyword_search=self._keyword_search,
            )
            await self._doc_repo.delete(d)
        await self._kb_repo.delete(kb)
        await self._session.commit()
        logger.info("KB_DELETED | kb_id=%s | documents=%d", kb_id, len(docs))
