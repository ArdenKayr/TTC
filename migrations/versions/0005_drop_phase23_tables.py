"""drop unused phase 2/3 tables (activities, billing) for the beta release

The tables were created up-front in 0001 but no code ever used them.
For the beta we keep only what works today; the tables will be re-created
by new migrations when their phases are actually built.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-16

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

request_status = postgresql.ENUM(
    "pending", "approved", "rejected", name="request_status", create_type=False
)
activity_status = postgresql.ENUM(
    "preparing", "active", "completed", "cancelled", name="activity_status", create_type=False
)
vote_poll_status = postgresql.ENUM(
    "not_requested",
    "pending_admin_approval",
    "posted",
    "closed",
    name="vote_poll_status",
    create_type=False,
)
afisha_status = postgresql.ENUM(
    "none", "requested", "published", name="afisha_status", create_type=False
)
billing_type = postgresql.ENUM("one_time", "monthly", name="billing_type", create_type=False)
target_type = postgresql.ENUM("all", "specific", name="target_type", create_type=False)
payment_status = postgresql.ENUM(
    "pending", "paid", "failed", "cancelled", name="payment_status", create_type=False
)

# request_status is NOT dropped: registration/university/alias tables still use it.
DROPPED_ENUMS = [
    activity_status,
    vote_poll_status,
    afisha_status,
    billing_type,
    target_type,
    payment_status,
]

NOW = sa.text("now()")


def upgrade() -> None:
    bind = op.get_bind()
    op.drop_table("transactions")
    op.drop_table("billing_subscriptions")
    op.drop_table("billing_requests")
    op.drop_table("activity_organizers")
    op.drop_constraint(
        "fk_activity_proposals_resulting_activity_id_activities",
        "activity_proposals",
        type_="foreignkey",
    )
    op.drop_table("activities")
    op.drop_table("activity_proposals")
    for enum in DROPPED_ENUMS:
        enum.drop(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for enum in DROPPED_ENUMS:
        enum.create(bind, checkfirst=True)

    op.create_table(
        "activity_proposals",
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("proposed_by", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("implementation_plan_url", sa.String(2048)),
        sa.Column("chat_url", sa.String(2048)),
        sa.Column("admin_comment_from_proposer", sa.Text()),
        sa.Column("wants_pre_vote", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("vote_poll_message_id", sa.BigInteger()),
        sa.Column(
            "vote_poll_status", vote_poll_status, nullable=False, server_default="not_requested"
        ),
        sa.Column("status", request_status, nullable=False, server_default="pending"),
        sa.Column("processed_by", sa.BigInteger()),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("admin_comment", sa.Text()),
        sa.Column("resulting_activity_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.ForeignKeyConstraint(
            ["proposed_by"], ["users.tg_id"], name="fk_activity_proposals_proposed_by_users"
        ),
        sa.ForeignKeyConstraint(
            ["processed_by"], ["users.tg_id"], name="fk_activity_proposals_processed_by_users"
        ),
    )
    op.create_index("ix_activity_proposals_status", "activity_proposals", ["status"])

    op.create_table(
        "activities",
        sa.Column("activity_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", activity_status, nullable=False, server_default="preparing"),
        sa.Column("implementation_plan_url", sa.String(2048)),
        sa.Column("chat_url", sa.String(2048)),
        sa.Column("supervising_admin_id", sa.BigInteger(), nullable=False),
        sa.Column("admin_comment", sa.Text()),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True)),
        sa.Column("afisha_status", afisha_status, nullable=False, server_default="none"),
        sa.Column("afisha_requested_at", sa.DateTime(timezone=True)),
        sa.Column("afisha_published_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.ForeignKeyConstraint(
            ["supervising_admin_id"],
            ["users.tg_id"],
            name="fk_activities_supervising_admin_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["proposal_id"],
            ["activity_proposals.proposal_id"],
            name="fk_activities_proposal_id_activity_proposals",
        ),
    )
    op.create_index("ix_activities_status", "activities", ["status"])

    op.create_foreign_key(
        "fk_activity_proposals_resulting_activity_id_activities",
        "activity_proposals",
        "activities",
        ["resulting_activity_id"],
        ["activity_id"],
    )

    op.create_table(
        "activity_organizers",
        sa.Column("activity_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organizer_id", sa.BigInteger(), primary_key=True),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["activities.activity_id"],
            name="fk_activity_organizers_activity_id_activities",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organizer_id"],
            ["users.tg_id"],
            name="fk_activity_organizers_organizer_id_users",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_activity_organizers_organizer_id", "activity_organizers", ["organizer_id"]
    )

    op.create_table(
        "billing_requests",
        sa.Column("billing_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("activity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("billing_type", billing_type, nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="RUB"),
        sa.Column("target_type", target_type, nullable=False),
        sa.Column("target_users_raw", postgresql.JSONB()),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", request_status, nullable=False, server_default="pending"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("approved_by", sa.BigInteger()),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["activities.activity_id"],
            name="fk_billing_requests_activity_id_activities",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.tg_id"], name="fk_billing_requests_created_by_users"
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"], ["users.tg_id"], name="fk_billing_requests_approved_by_users"
        ),
    )
    op.create_index("ix_billing_requests_status", "billing_requests", ["status"])

    op.create_table(
        "billing_subscriptions",
        sa.Column("billing_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), primary_key=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["billing_id"],
            ["billing_requests.billing_id"],
            name="fk_billing_subscriptions_billing_id_billing_requests",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.tg_id"], name="fk_billing_subscriptions_user_id_users"
        ),
    )
    op.create_index("ix_billing_subscriptions_user_id", "billing_subscriptions", ["user_id"])

    op.create_table(
        "transactions",
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("billing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("billing_period", sa.Date()),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("payment_status", payment_status, nullable=False, server_default="pending"),
        sa.Column("payment_provider_reference", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.ForeignKeyConstraint(
            ["billing_id"],
            ["billing_requests.billing_id"],
            name="fk_transactions_billing_id_billing_requests",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.tg_id"], name="fk_transactions_user_id_users"
        ),
    )
    op.create_index("ix_transactions_billing_id", "transactions", ["billing_id"])
    op.create_index("ix_transactions_user_id", "transactions", ["user_id"])
    op.create_index(
        "uq_transactions_one_time",
        "transactions",
        ["billing_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("billing_period IS NULL"),
    )
    op.create_index(
        "uq_transactions_period",
        "transactions",
        ["billing_id", "user_id", "billing_period"],
        unique=True,
        postgresql_where=sa.text("billing_period IS NOT NULL"),
    )
