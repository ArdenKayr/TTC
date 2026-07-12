import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from bot.db.base import Base
from bot.db.models._types import request_status_enum
from bot.enums import RequestStatus


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


class UniversityRequest(Base):
    """Заявка пользователя на добавление нового вуза в справочник."""

    __tablename__ = "university_requests"

    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Not an FK to users: the applicant has no users row until registration is approved.
    tg_id: Mapped[int] = mapped_column(sa.BigInteger, index=True)
    applicant_name: Mapped[str] = mapped_column(sa.String(255))
    applicant_username: Mapped[str | None] = mapped_column(sa.String(32))
    name: Mapped[str] = mapped_column(sa.String(255))
    aliases: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=sa.text("'[]'::jsonb")
    )
    link: Mapped[str] = mapped_column(sa.String(512))
    status: Mapped[RequestStatus] = mapped_column(
        request_status_enum,
        default=RequestStatus.PENDING,
        server_default=RequestStatus.PENDING.value,
        index=True,
    )
    processed_by: Mapped[int | None] = mapped_column(sa.ForeignKey("users.tg_id"))
    processed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    admin_comment: Mapped[str | None] = mapped_column(sa.Text)
    created_university_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("universities.university_id")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class AliasSuggestion(Base):
    """Предложение варианта поиска (сокращения) для существующего вуза."""

    __tablename__ = "alias_suggestions"
    __table_args__ = (
        sa.Index("ix_alias_suggestions_tg_id_university_id", "tg_id", "university_id"),
    )

    suggestion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    university_id: Mapped[int] = mapped_column(
        sa.ForeignKey("universities.university_id", ondelete="CASCADE")
    )
    tg_id: Mapped[int] = mapped_column(sa.BigInteger)
    applicant_name: Mapped[str] = mapped_column(sa.String(255))
    applicant_username: Mapped[str | None] = mapped_column(sa.String(32))
    alias_text: Mapped[str] = mapped_column(sa.String(255))
    status: Mapped[RequestStatus] = mapped_column(
        request_status_enum,
        default=RequestStatus.PENDING,
        server_default=RequestStatus.PENDING.value,
        index=True,
    )
    processed_by: Mapped[int | None] = mapped_column(sa.ForeignKey("users.tg_id"))
    processed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
