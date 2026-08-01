import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from bot.db.base import Base
from bot.db.models._types import request_status_enum
from bot.enums import RequestStatus


class RegistrationRequest(Base):
    __tablename__ = "registration_requests"
    __table_args__ = (
        sa.Index("ix_registration_requests_tg_id_status", "tg_id", "status"),
    )

    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Not an FK to users: the applicant usually has no users row yet.
    tg_id: Mapped[int] = mapped_column(sa.BigInteger, index=True)
    # Имя/ник — как человек просит к нему обращаться (не паспортное ФИО).
    full_name: Mapped[str] = mapped_column(sa.String(255))
    university_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("universities.university_id", ondelete="SET NULL")
    )
    university_group: Mapped[str | None] = mapped_column(sa.String(50))
    birth_date: Mapped[date]
    # «О себе» — для тех, кто не учится в вузе СПб.
    about_text: Mapped[str | None] = mapped_column(sa.Text)
    # Заполнено, если человек подал заявку на новый вуз: карточка регистрации
    # отправляется админам только после решения по этой заявке.
    university_request_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey(
            "university_requests.request_id",
            name="fk_reg_requests_university_request",
            ondelete="SET NULL",
        )
    )
    raw_input_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[RequestStatus] = mapped_column(
        request_status_enum,
        default=RequestStatus.PENDING,
        server_default=RequestStatus.PENDING.value,
        index=True,
    )
    attempt_number: Mapped[int]
    next_allowed_attempt: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    processed_by: Mapped[int | None] = mapped_column(
        sa.ForeignKey("users.tg_id", ondelete="SET NULL")
    )
    processed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    admin_comment: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
