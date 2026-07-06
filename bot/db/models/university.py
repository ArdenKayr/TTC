from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from bot.db.base import Base


class University(Base):
    __tablename__ = "universities"
    __table_args__ = (
        sa.Index(
            "ix_universities_canonical_name_trgm",
            "canonical_name",
            postgresql_using="gin",
            postgresql_ops={"canonical_name": "gin_trgm_ops"},
        ),
    )

    university_id: Mapped[int] = mapped_column(primary_key=True)
    canonical_name: Mapped[str] = mapped_column(sa.String(255), unique=True)
    city: Mapped[str | None] = mapped_column(sa.String(255))
    is_verified: Mapped[bool] = mapped_column(default=True, server_default=sa.true())
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class UniversityAlias(Base):
    __tablename__ = "university_aliases"
    __table_args__ = (
        sa.Index(
            "ix_university_aliases_alias_text_trgm",
            "alias_text",
            postgresql_using="gin",
            postgresql_ops={"alias_text": "gin_trgm_ops"},
        ),
    )

    alias_id: Mapped[int] = mapped_column(primary_key=True)
    university_id: Mapped[int] = mapped_column(
        sa.ForeignKey("universities.university_id", ondelete="CASCADE")
    )
    alias_text: Mapped[str] = mapped_column(sa.String(255))
