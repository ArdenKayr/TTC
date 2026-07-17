"""activities and votes for the beta (lean redesign)

Two independent request types decided by admins:
- activity_requests -> approved -> activities (card in the Афиша topic,
  author auto-promoted to organizer)
- vote_requests -> approved -> bot posts a poll to the Голосования topic

This is NOT the old phase-2 schema dropped in 0005: no proposals/organizers
join table, a single organizer per activity, no pre-vote coupling.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-18

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

request_status = postgresql.ENUM(
    "pending", "approved", "rejected", name="request_status", create_type=False
)
activity_status = postgresql.ENUM(
    "active", "completed", "cancelled", name="activity_status", create_type=False
)

NOW = sa.text("now()")


def upgrade() -> None:
    activity_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "activity_requests",
        sa.Column("request_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tg_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("extra_url", sa.String(512), nullable=True),
        sa.Column("status", request_status, nullable=False, server_default="pending"),
        sa.Column("processed_by", sa.BigInteger(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.ForeignKeyConstraint(
            ["tg_id"], ["users.tg_id"], name="fk_activity_requests_tg_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["processed_by"], ["users.tg_id"], name="fk_activity_requests_processed_by_users"
        ),
    )
    op.create_index("ix_activity_requests_status", "activity_requests", ["status"])

    op.create_table(
        "activities",
        sa.Column("activity_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organizer_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("extra_url", sa.String(512), nullable=True),
        sa.Column("status", activity_status, nullable=False, server_default="active"),
        sa.Column("afisha_message_id", sa.BigInteger(), nullable=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.ForeignKeyConstraint(
            ["organizer_id"], ["users.tg_id"], name="fk_activities_organizer_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["activity_requests.request_id"],
            name="fk_activities_request_id_activity_requests",
        ),
    )
    op.create_index("ix_activities_organizer_id", "activities", ["organizer_id"])
    op.create_index("ix_activities_status", "activities", ["status"])

    op.create_table(
        "vote_requests",
        sa.Column("request_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tg_id", sa.BigInteger(), nullable=False),
        sa.Column("question", sa.String(300), nullable=False),
        sa.Column("options", postgresql.JSONB(), nullable=False),
        sa.Column("status", request_status, nullable=False, server_default="pending"),
        sa.Column("processed_by", sa.BigInteger(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("poll_message_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.ForeignKeyConstraint(["tg_id"], ["users.tg_id"], name="fk_vote_requests_tg_id_users"),
        sa.ForeignKeyConstraint(
            ["processed_by"], ["users.tg_id"], name="fk_vote_requests_processed_by_users"
        ),
    )
    op.create_index("ix_vote_requests_status", "vote_requests", ["status"])


def downgrade() -> None:
    op.drop_table("vote_requests")
    op.drop_table("activities")
    op.drop_table("activity_requests")
    activity_status.drop(op.get_bind(), checkfirst=True)
