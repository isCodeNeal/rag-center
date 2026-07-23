"""retrieval_logs: 新增 kb_ids JSONB 字段，支持多库并行召回记录

Revision ID: 0009_retrieval_log_kb_ids
Revises: 0008_document_source_file
Create Date: 2026-07-23 00:00:00.000000

字段可空，不影响旧数据。单库检索时保持 null，多库检索时写入参与检索的
完整 kb_id 列表。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_retrieval_log_kb_ids"
down_revision: Union[str, None] = "0008_document_source_file"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "retrieval_logs",
        sa.Column("kb_ids", postgresql.JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("retrieval_logs", "kb_ids")
