from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bot.db.base import Base
from bot.db.models._types import actor_type_enum
from bot.enums import ActorType


class AuditLog(Base):
    """Append-only: no application code path may UPDATE or DELETE rows here."""

    __tablename__ = "audit_log"

    log_id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True)
    actor_tg_id: Mapped[int | None] = mapped_column(sa.ForeignKey("users.tg_id"), index=True)
    actor_type: Mapped[ActorType] = mapped_column(
        actor_type_enum, default=ActorType.ADMIN, server_default=ActorType.ADMIN.value
    )
    # Varchar, not a DB enum: the action list grows with every feature.
    action_type: Mapped[str] = mapped_column(sa.String(50), index=True)
    target_tg_id: Mapped[int | None] = mapped_column(sa.BigInteger, index=True)
    target_entity_type: Mapped[str | None] = mapped_column(sa.String(30))
    # Text on purpose: referenced IDs are polymorphic (bigint tg_id vs UUID).
    target_entity_id: Mapped[str | None] = mapped_column(sa.String(64))
    reason: Mapped[str | None] = mapped_column(sa.Text)
    meta: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()"), index=True
    )
