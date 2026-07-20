"""Document ORM 模型。"""
from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import DocumentStatus
from app.utils.id_generator import new_document_id


class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    # document_id —— 由 RAG 中台生成（UUID）
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_document_id)
    # tenant_id —— 由调用方提供
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    kb_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    # source_type: "text" / "txt" / "md"（第一阶段仅接受纯文本上传）
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="text")
    status: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DocumentStatus.PROCESSING.value
    )
