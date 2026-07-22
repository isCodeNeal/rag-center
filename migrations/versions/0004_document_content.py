"""documents.content

Revision ID: 0004_document_content
Revises: 0003_kb_settings
Create Date: 2026-07-21 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_document_content"
down_revision: Union[str, None] = "0003_kb_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("documents", "content")
