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
    full_name: Mapped[str] = mapped_column(sa.String(255))
    university_id: Mapped[int] = mapped_column(sa.ForeignKey("universities.university_id"))
    university_group: Mapped[str] = mapped_column(sa.String(50))
    birth_date: Mapped[date]
    raw_input_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[RequestStatus] = mapped_column(
        request_status_enum,
        default=RequestStatus.PENDING,
        server_default=RequestStatus.PENDING.value,
        index=True,
    )
    attempt_number: Mapped[int]
    next_allowed_attempt: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    processed_by: Mapped[int | None] = mapped_column(sa.ForeignKey("users.tg_id"))
    processed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    admin_comment: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
