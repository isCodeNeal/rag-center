"""KnowledgeBase ORM 模型。"""
from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.utils.id_generator import new_kb_id


class KnowledgeBase(Base, TimestampMixin):
    __tablename__ = "knowledge_bases"

    # kb_id —— 由 RAG 中台生成（UUID）
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_kb_id)
    # tenant_id —— 由调用方提供（业务上下文）
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
