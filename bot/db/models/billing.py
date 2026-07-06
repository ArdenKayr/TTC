import uuid
from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from bot.db.base import Base
from bot.db.models._types import billing_type_enum, payment_status_enum, request_status_enum, target_type_enum
from bot.enums import BillingType, PaymentStatus, RequestStatus, TargetType


class BillingRequest(Base):
    __tablename__ = "billing_requests"

    billing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    activity_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("activities.activity_id"))
    created_by: Mapped[int] = mapped_column(sa.ForeignKey("users.tg_id"))
    billing_type: Mapped[BillingType] = mapped_column(billing_type_enum)
    amount: Mapped[Decimal] = mapped_column(sa.Numeric(10, 2))
    currency: Mapped[str] = mapped_column(sa.String(3), default="RUB", server_default="RUB")
    target_type: Mapped[TargetType] = mapped_column(target_type_enum)
    target_users_raw: Mapped[list | None] = mapped_column(JSONB)
    description: Mapped[str] = mapped_column(sa.Text)
    status: Mapped[RequestStatus] = mapped_column(
        request_status_enum,
        default=RequestStatus.PENDING,
        server_default=RequestStatus.PENDING.value,
        index=True,
    )
    # Whether an approved billing is still collecting; independent from approval status.
    is_active: Mapped[bool] = mapped_column(default=True, server_default=sa.true())
    approved_by: Mapped[int | None] = mapped_column(sa.ForeignKey("users.tg_id"))
    approved_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class BillingSubscription(Base):
    __tablename__ = "billing_subscriptions"

    billing_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("billing_requests.billing_id"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        sa.ForeignKey("users.tg_id"), primary_key=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(default=True, server_default=sa.true())
    enrolled_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        # Plain UNIQUE can't cover the one-time case: Postgres treats NULLs as distinct.
        sa.Index(
            "uq_transactions_one_time",
            "billing_id",
            "user_id",
            unique=True,
            postgresql_where=sa.text("billing_period IS NULL"),
        ),
        sa.Index(
            "uq_transactions_period",
            "billing_id",
            "user_id",
            "billing_period",
            unique=True,
            postgresql_where=sa.text("billing_period IS NOT NULL"),
        ),
    )

    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    billing_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("billing_requests.billing_id"), index=True
    )
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.tg_id"), index=True)
    billing_period: Mapped[date | None]
    amount: Mapped[Decimal] = mapped_column(sa.Numeric(10, 2))
    payment_status: Mapped[PaymentStatus] = mapped_column(
        payment_status_enum,
        default=PaymentStatus.PENDING,
        server_default=PaymentStatus.PENDING.value,
    )
    payment_provider_reference: Mapped[str | None] = mapped_column(sa.String(255))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()"), onupdate=sa.func.now()
    )
