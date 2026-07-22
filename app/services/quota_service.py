"""DB 配额检查：知识库数、单库文档数、并发 PROCESSING 数。

超限统一抛 QuotaExceeded(20014)，msg 用人类可读文案。日检索量走 Redis
（RateLimitService），不在这里。
"""
from __future__ import annotations

from app.core.exceptions import QuotaExceeded
from app.repositories.document_repository import DocumentRepository
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.tenant.plan_resolver import PlanContext


class QuotaService:
    def __init__(
        self,
        *,
        kb_repository: KnowledgeBaseRepository,
        document_repository: DocumentRepository,
    ):
        self._kb_repo = kb_repository
        self._doc_repo = document_repository

    async def check_can_create_kb(self, tenant_id: str, plan: PlanContext) -> None:
        count = await self._kb_repo.count_by_tenant(tenant_id)
        if count >= plan.limits.max_kb:
            raise QuotaExceeded(
                msg=f"{plan.plan} 档最多创建 {plan.limits.max_kb} 个知识库，请升级套餐",
                detail=f"tenant_id={tenant_id} kb_count={count}",
            )

    async def check_can_upload(self, tenant_id: str, kb_id: str, plan: PlanContext) -> None:
        # 单库文档数上限
        doc_count = await self._doc_repo.count_by_kb(kb_id)
        if doc_count >= plan.limits.max_documents_per_kb:
            raise QuotaExceeded(
                msg=f"{plan.plan} 档单库最多 {plan.limits.max_documents_per_kb} 个文档，请升级套餐",
                detail=f"kb_id={kb_id} doc_count={doc_count}",
            )
        # 并发 PROCESSING 上限
        await self.check_processing_capacity(tenant_id, plan)

    async def check_processing_capacity(self, tenant_id: str, plan: PlanContext) -> None:
        processing = await self._doc_repo.count_processing_by_tenant(tenant_id)
        if processing >= plan.limits.max_processing_documents:
            raise QuotaExceeded(
                msg=f"{plan.plan} 档最多同时索引 {plan.limits.max_processing_documents} 个文档，请等待当前任务完成",
                detail=f"tenant_id={tenant_id} processing={processing}",
            )

    async def get_kb_count(self, tenant_id: str) -> int:
        return await self._kb_repo.count_by_tenant(tenant_id)
