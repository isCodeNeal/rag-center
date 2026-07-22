"""RetrievalLog ORM 模型 —— 每次 RAG 检索调用对应一行记录，用于可观测性。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.utils.id_generator import new_retrieval_log_id


class RetrievalLog(Base):
    __tablename__ = "retrieval_logs"

    # retrieval_log_id —— 由 RAG 中台生成（UUID）
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_retrieval_log_id)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    kb_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # user_id —— 由调用方提供；用于记录日志以及未来的 ACL 过滤
    user_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    # 提问语义优化链路（可空）：LLM 改写后的句子、词表扩展后的最终检索句
    effective_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 返回的 chunk 快照（document_id、chunk_id、title、score 等）
    retrieved_chunks: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    vector_store: Mapped[str] = mapped_column(String(64), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
