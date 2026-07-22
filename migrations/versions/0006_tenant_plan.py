"""tenants.plan

Revision ID: 0006_tenant_plan
Revises: 0005_document_error_message
Create Date: 2026-07-22 00:00:00.000000

数据迁移策略：
- 升级前已存在的租户改为 standard（避免老用户突然降档）；
- tenant_demo 改为 pro；
- 此后 create_tenant 新建的租户默认 free（由列默认值 + 脚本控制）。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_tenant_plan"
down_revision: Union[str, None] = "0005_document_error_message"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("plan", sa.String(length=32), nullable=False, server_default="free"),
    )
    # 老租户默认升为 standard，避免突然降档。
    op.execute("UPDATE tenants SET plan = 'standard'")
    # 演示租户给最高档 pro。
    op.execute("UPDATE tenants SET plan = 'pro' WHERE id = 'tenant_demo'")


def downgrade() -> None:
    op.drop_column("tenants", "plan")
