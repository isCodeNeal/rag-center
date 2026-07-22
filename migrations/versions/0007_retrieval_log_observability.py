"""retrieval_logs: 新增 trace_id（Langfuse）和 profile（检索策略档位）

Revision ID: 0007_retrieval_log_observability
Revises: 0006_tenant_plan
Create Date: 2026-07-22 00:00:00.000000

所有字段均可空，不影响旧数据。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_retrieval_log_observability"
down_revision: Union[str, None] = "0006_tenant_plan"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("retrieval_logs", sa.Column("trace_id", sa.String(64), nullable=True))
    op.add_column("retrieval_logs", sa.Column("profile", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("retrieval_logs", "profile")
    op.drop_column("retrieval_logs", "trace_id")
