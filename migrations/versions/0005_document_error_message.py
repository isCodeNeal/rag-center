"""documents.error_message

Revision ID: 0005_document_error_message
Revises: 0004_document_content
Create Date: 2026-07-21 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_document_error_message"
down_revision: Union[str, None] = "0004_document_content"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("error_message", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "error_message")
