"""knowledge_bases.settings + retrieval_logs 改写链路字段

Revision ID: 0003_kb_settings
Revises: 0002_auth
Create Date: 2026-07-21 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0003_kb_settings"
down_revision: Union[str, None] = "0002_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "knowledge_bases",
        sa.Column("settings", JSONB(), nullable=False, server_default="{}"),
    )
    # 提问语义优化链路，便于后续分析改写效果（可空）
    op.add_column("retrieval_logs", sa.Column("effective_query", sa.Text(), nullable=True))
    op.add_column("retrieval_logs", sa.Column("search_query", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("retrieval_logs", "search_query")
    op.drop_column("retrieval_logs", "effective_query")
    op.drop_column("knowledge_bases", "settings")
