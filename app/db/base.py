"""声明式 Base 和共享的模型 metadata。

（在底部）`import app.models` 确保所有 ORM 模型都注册到
`Base.metadata` 上，这是 Alembic 的 autogenerate 和 `create_all` 所依赖的。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有 ORM 模型的 Base 类。"""


class TimestampMixin:
    """添加由数据库管理的 created_at / updated_at 列。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
