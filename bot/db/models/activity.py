import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from bot.db.base import Base
from bot.db.models._types import activity_status_enum, request_status_enum
from bot.enums import ActivityStatus, RequestStatus


class ActivityRequest(Base):
    """Заявка на мероприятие: подаёт зарегистрированный, решает админ."""

    __tablename__ = "activity_requests"

    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tg_id: Mapped[int] = mapped_column(sa.ForeignKey("users.tg_id"))
    title: Mapped[str] = mapped_column(sa.String(100))
    description: Mapped[str] = mapped_column(sa.Text)
    extra_url: Mapped[str | None] = mapped_column(sa.String(512))
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


class Activity(Base):
    """Одобренное мероприятие: живёт в Афише, автор — организатор."""

    __tablename__ = "activities"

    activity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organizer_id: Mapped[int] = mapped_column(sa.ForeignKey("users.tg_id"), index=True)
    title: Mapped[str] = mapped_column(sa.String(100))
    description: Mapped[str] = mapped_column(sa.Text)
    extra_url: Mapped[str | None] = mapped_column(sa.String(512))
    status: Mapped[ActivityStatus] = mapped_column(
        activity_status_enum,
        default=ActivityStatus.ACTIVE,
        server_default=ActivityStatus.ACTIVE.value,
        index=True,
    )
    # id сообщения-карточки в топике «Афиша» — чтобы пометить её при завершении/отмене.
    afisha_message_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    request_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("activity_requests.request_id")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()"), onupdate=sa.func.now()
    )


class VoteRequest(Base):
    """Заявка на голосование: одобренный опрос бот публикует в топик «Голосования»."""

    __tablename__ = "vote_requests"

    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tg_id: Mapped[int] = mapped_column(sa.ForeignKey("users.tg_id"))
    question: Mapped[str] = mapped_column(sa.String(300))
    options: Mapped[list[str]] = mapped_column(JSONB)
    status: Mapped[RequestStatus] = mapped_column(
        request_status_enum,
        default=RequestStatus.PENDING,
        server_default=RequestStatus.PENDING.value,
        index=True,
    )
    processed_by: Mapped[int | None] = mapped_column(sa.ForeignKey("users.tg_id"))
    processed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    poll_message_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
