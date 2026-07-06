import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from bot.db.base import Base
from bot.db.models._types import (
    activity_status_enum,
    afisha_status_enum,
    request_status_enum,
    vote_poll_status_enum,
)
from bot.enums import ActivityStatus, AfishaStatus, RequestStatus, VotePollStatus


class ActivityProposal(Base):
    __tablename__ = "activity_proposals"

    proposal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    proposed_by: Mapped[int] = mapped_column(sa.ForeignKey("users.tg_id"))
    title: Mapped[str] = mapped_column(sa.String(255))
    description: Mapped[str] = mapped_column(sa.Text)
    implementation_plan_url: Mapped[str | None] = mapped_column(sa.String(2048))
    chat_url: Mapped[str | None] = mapped_column(sa.String(2048))
    admin_comment_from_proposer: Mapped[str | None] = mapped_column(sa.Text)
    wants_pre_vote: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    vote_poll_message_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    vote_poll_status: Mapped[VotePollStatus] = mapped_column(
        vote_poll_status_enum,
        default=VotePollStatus.NOT_REQUESTED,
        server_default=VotePollStatus.NOT_REQUESTED.value,
    )
    status: Mapped[RequestStatus] = mapped_column(
        request_status_enum,
        default=RequestStatus.PENDING,
        server_default=RequestStatus.PENDING.value,
        index=True,
    )
    processed_by: Mapped[int | None] = mapped_column(sa.ForeignKey("users.tg_id"))
    processed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    admin_comment: Mapped[str | None] = mapped_column(sa.Text)
    resulting_activity_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("activities.activity_id", use_alter=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class Activity(Base):
    __tablename__ = "activities"

    activity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(sa.String(255))
    description: Mapped[str] = mapped_column(sa.Text)
    status: Mapped[ActivityStatus] = mapped_column(
        activity_status_enum,
        default=ActivityStatus.PREPARING,
        server_default=ActivityStatus.PREPARING.value,
        index=True,
    )
    implementation_plan_url: Mapped[str | None] = mapped_column(sa.String(2048))
    chat_url: Mapped[str | None] = mapped_column(sa.String(2048))
    supervising_admin_id: Mapped[int] = mapped_column(sa.ForeignKey("users.tg_id"))
    admin_comment: Mapped[str | None] = mapped_column(sa.Text)
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("activity_proposals.proposal_id")
    )
    afisha_status: Mapped[AfishaStatus] = mapped_column(
        afisha_status_enum, default=AfishaStatus.NONE, server_default=AfishaStatus.NONE.value
    )
    afisha_requested_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    afisha_published_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()"), onupdate=sa.func.now()
    )


class ActivityOrganizer(Base):
    __tablename__ = "activity_organizers"

    activity_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("activities.activity_id", ondelete="CASCADE"), primary_key=True
    )
    organizer_id: Mapped[int] = mapped_column(
        sa.ForeignKey("users.tg_id", ondelete="CASCADE"), primary_key=True, index=True
    )
    added_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
