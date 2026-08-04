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
    # Автор. Пусто — если человека удалили из базы: заявка остаётся, но уже
    # «от удалённого пользователя». Так владелец может удалить кого угодно,
    # не разрушая историю (см. ondelete="SET NULL" у всех ссылок на людей).
    tg_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("users.tg_id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(sa.String(100))
    description: Mapped[str] = mapped_column(sa.Text)
    # Обложка поста в Афише — номер фотографии в хранилище Telegram. Шаг
    # обязательный; пусто бывает только у заявок, поданных до его появления.
    photo_file_id: Mapped[str | None] = mapped_column(sa.Text)
    # Что нужно, чтобы мероприятие состоялось: люди, деньги, помещение, реквизит.
    # Пусто бывает только у заявок, поданных до появления этого шага в анкете.
    needs_text: Mapped[str | None] = mapped_column(sa.Text)
    organizers_text: Mapped[str | None] = mapped_column(sa.Text)  # кто проводит, @ники
    plan_url: Mapped[str | None] = mapped_column(sa.String(512))  # план реализации
    chat_url: Mapped[str | None] = mapped_column(sa.String(512))  # беседа мероприятия
    admin_comment: Mapped[str | None] = mapped_column(sa.Text)  # комментарий админам
    status: Mapped[RequestStatus] = mapped_column(
        request_status_enum,
        default=RequestStatus.PENDING,
        server_default=RequestStatus.PENDING.value,
        index=True,
    )
    processed_by: Mapped[int | None] = mapped_column(
        sa.ForeignKey("users.tg_id", ondelete="SET NULL")
    )
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
    # Организатор. Пусто — если человека удалили: мероприятие остаётся в Афише.
    organizer_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("users.tg_id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(sa.String(100))
    description: Mapped[str] = mapped_column(sa.Text)
    # Обложка поста в Афише — переносится из заявки.
    photo_file_id: Mapped[str | None] = mapped_column(sa.Text)
    # Что нужно для проведения — переносится из заявки и показывается в Афише.
    needs_text: Mapped[str | None] = mapped_column(sa.Text)
    organizers_text: Mapped[str | None] = mapped_column(sa.Text)
    plan_url: Mapped[str | None] = mapped_column(sa.String(512))
    chat_url: Mapped[str | None] = mapped_column(sa.String(512))
    status: Mapped[ActivityStatus] = mapped_column(
        activity_status_enum,
        default=ActivityStatus.ACTIVE,
        server_default=ActivityStatus.ACTIVE.value,
        index=True,
    )
    # id сообщения-карточки в топике «Афиша» — чтобы пометить её при завершении/отмене.
    afisha_message_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    # Карточка ушла подписью под картинкой (иначе — отдельным сообщением под
    # ней: в подпись Telegram пускает только 1024 символа, а описание бывает
    # длиннее). От этого зависит, что править при закрытии — подпись или текст.
    afisha_is_caption: Mapped[bool] = mapped_column(
        sa.Boolean, default=False, server_default=sa.false()
    )
    request_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("activity_requests.request_id", ondelete="SET NULL")
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
    # Автор. Пусто — если человека удалили из базы.
    tg_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("users.tg_id", ondelete="SET NULL")
    )
    question: Mapped[str] = mapped_column(sa.String(300))
    options: Mapped[list[str]] = mapped_column(JSONB)
    # Анонимный опрос — видно только счётчики; открытый — видно, кто как ответил.
    is_anonymous: Mapped[bool] = mapped_column(
        sa.Boolean, default=True, server_default=sa.true()
    )
    status: Mapped[RequestStatus] = mapped_column(
        request_status_enum,
        default=RequestStatus.PENDING,
        server_default=RequestStatus.PENDING.value,
        index=True,
    )
    processed_by: Mapped[int | None] = mapped_column(
        sa.ForeignKey("users.tg_id", ondelete="SET NULL")
    )
    processed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    poll_message_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
