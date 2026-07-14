from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bot.db.base import Base


class PermissionGroup(Base):
    """Группа прав: именованный набор модулей, который выдаётся людям целиком."""

    __tablename__ = "permission_groups"

    group_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(100), unique=True)
    # Список ключей модулей из PermissionModule, например ["registration", "content"].
    modules: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=sa.text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()"), onupdate=sa.func.now()
    )
