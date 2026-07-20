"""初始 schema：knowledge_bases、documents、chunks、retrieval_logs + pgvector

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-06 00:00:00.000000
"""
from typing import Sequence, Union

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.config import settings

# 修订版本标识，供 Alembic 使用。
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = settings.embedding_dim


def upgrade() -> None:
    # vector 列类型需要先启用 pgvector 扩展
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "knowledge_bases",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_knowledge_bases_tenant_id", "knowledge_bases", ["tenant_id"])

    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("kb_id", sa.String(length=64), sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False, server_default="text"),
        sa.Column("status", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_documents_tenant_id", "documents", ["tenant_id"])
    op.create_index("ix_documents_kb_id", "documents", ["kb_id"])

    op.create_table(
        "chunks",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("kb_id", sa.String(length=64), sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.String(length=64), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_chunks_tenant_id", "chunks", ["tenant_id"])
    op.create_index("ix_chunks_kb_id", "chunks", ["kb_id"])
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])

    op.create_table(
        "retrieval_logs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("kb_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("retrieved_chunks", postgresql.JSONB(), nullable=True),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("vector_store", sa.String(length=64), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_retrieval_logs_tenant_id", "retrieval_logs", ["tenant_id"])
    op.create_index("ix_retrieval_logs_kb_id", "retrieval_logs", ["kb_id"])
    op.create_index("ix_retrieval_logs_user_id", "retrieval_logs", ["user_id"])


def downgrade() -> None:
    op.drop_table("retrieval_logs")
    op.drop_table("chunks")
    op.drop_table("documents")
    op.drop_table("knowledge_bases")
    # 有意保留该扩展，不做移除。
