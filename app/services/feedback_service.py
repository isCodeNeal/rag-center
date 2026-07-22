"""检索反馈 service：将 user_feedback score 写入 Langfuse。

处理逻辑：
1. 若传 log_id：查 retrieval_logs，校验 tenant_id 匹配且 trace_id 一致。
2. 调 Langfuse SDK 在 trace_id 上创建 score。
3. LANGFUSE_ENABLED=false 或写入异常时抛 FeedbackFailed(20020)。
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import FeedbackFailed, FeedbackInvalid
from app.core.logging import get_logger
from app.observability.langfuse_client import get_langfuse_client
from app.repositories.retrieval_log_repository import RetrievalLogRepository
from app.schemas.feedback import FeedbackData, FeedbackRequest

logger = get_logger(__name__)


class FeedbackService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        retrieval_log_repository: RetrievalLogRepository,
    ):
        self._session = session
        self._log_repo = retrieval_log_repository

    async def submit(
        self, req: FeedbackRequest, tenant_id: str
    ) -> FeedbackData:
        # 1. 若传 log_id，校验租户权限与 trace_id 一致性
        if req.log_id is not None:
            log = await self._log_repo.get(req.log_id)
            if log is None or log.tenant_id != tenant_id:
                raise FeedbackInvalid(
                    detail=f"log_id={req.log_id} not found or tenant mismatch"
                )
            if log.trace_id != req.trace_id:
                raise FeedbackInvalid(
                    detail=(
                        f"trace_id mismatch: log has {log.trace_id}, "
                        f"request has {req.trace_id}"
                    )
                )

        # 2. 写入 Langfuse
        lf = get_langfuse_client()
        if lf is None:
            raise FeedbackFailed(detail="Langfuse not enabled or client unavailable")

        feedback_id = str(uuid.uuid4())
        try:
            lf.score(
                trace_id=req.trace_id,
                name="user_feedback",
                value=float(req.score),
                comment=req.comment,
                id=feedback_id,
            )
            lf.flush()
        except Exception as exc:  # noqa: BLE001
            logger.error("LANGFUSE_SCORE_WRITE_FAILED | trace_id=%s | error=%s", req.trace_id, exc)
            raise FeedbackFailed(detail=str(exc))

        logger.info(
            "FEEDBACK_SUBMITTED | trace_id=%s | log_id=%s | score=%d",
            req.trace_id,
            req.log_id,
            req.score,
        )
        return FeedbackData(
            feedback_id=feedback_id,
            trace_id=req.trace_id,
            log_id=req.log_id,
            score=req.score,
        )
