"""Chunk ORM 模型。

同时保存 chunk 的元数据和它的 embedding 向量（pgvector）。第一阶段中，
基于 pgvector 的 VectorStore 会读写这张表；如果后续引入其他向量存储，
向量列可以迁移，元数据仍保留在这里。
"""
from __future__ import annotations

from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.base import Base
from sqlalchemy import DateTime, func
from datetime import datetime

from app.utils.id_generator import new_chunk_id


class Chunk(Base):
    __tablename__ = "chunks"

    # chunk_id —— 由 RAG 中台生成（UUID）
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_chunk_id)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    kb_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # "metadata" 是 SQLAlchemy Declarative 的保留字，因此这里将属性重命名，
    # 但数据库列名仍保持为 "metadata"。
    chunk_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    embedding: Mapped[list[float]] = mapped_column(
        Vector(settings.embedding_dim), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
