"""documents: 新增 source_file_path 和 source_filename

Revision ID: 0008_document_source_file
Revises: 0007_retrieval_log_observability
Create Date: 2026-07-22 00:00:00.000000

新增两列，均可空，不影响旧数据：
- source_file_path: 原文件存盘路径（multipart upload 时填入，JSON upload 为 null）
- source_filename: 原始文件名（同上）
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_document_source_file"
down_revision: Union[str, None] = "0007_retrieval_log_observability"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("source_file_path", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("source_filename", sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "source_filename")
    op.drop_column("documents", "source_file_path")
