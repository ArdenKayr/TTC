from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bot.db.base import Base
from bot.db.models._types import user_role_enum
from bot.enums import UserRole


class User(Base):
    __tablename__ = "users"

    tg_id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(sa.String(32), index=True)
    display_name: Mapped[str] = mapped_column(sa.String(255))
    university_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("universities.university_id")
    )
    university_group: Mapped[str | None] = mapped_column(sa.String(50))
    birth_date: Mapped[date | None]
    current_role: Mapped[UserRole] = mapped_column(
        user_role_enum, default=UserRole.USER, server_default=UserRole.USER.value
    )
    role_before_ban: Mapped[UserRole | None] = mapped_column(user_role_enum)
    custom_permissions: Mapped[dict | None] = mapped_column(JSONB)
    banned_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    banned_reason: Mapped[str | None] = mapped_column(sa.Text)
    registration_date: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()"), onupdate=sa.func.now()
    )
