"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-07

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

user_role = postgresql.ENUM(
    "user", "organizer", "admin", "custom", "banned", name="user_role", create_type=False
)
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
actor_type = postgresql.ENUM("admin", "system", name="actor_type", create_type=False)

ALL_ENUMS = [
    user_role,
    request_status,
    activity_status,
    vote_poll_status,
    afisha_status,
    billing_type,
    target_type,
    payment_status,
    actor_type,
]

NOW = sa.text("now()")


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for enum in ALL_ENUMS:
        enum.create(bind, checkfirst=True)

    op.create_table(
        "universities",
        sa.Column("university_id", sa.Integer(), primary_key=True),
        sa.Column("canonical_name", sa.String(255), nullable=False),
        sa.Column("city", sa.String(255)),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("canonical_name", name="uq_universities_canonical_name"),
    )
    op.create_index(
        "ix_universities_canonical_name_trgm",
        "universities",
        ["canonical_name"],
        postgresql_using="gin",
        postgresql_ops={"canonical_name": "gin_trgm_ops"},
    )

    op.create_table(
        "university_aliases",
        sa.Column("alias_id", sa.Integer(), primary_key=True),
        sa.Column("university_id", sa.Integer(), nullable=False),
        sa.Column("alias_text", sa.String(255), nullable=False),
        sa.ForeignKeyConstraint(
            ["university_id"],
            ["universities.university_id"],
            name="fk_university_aliases_university_id_universities",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_university_aliases_alias_text_trgm",
        "university_aliases",
        ["alias_text"],
        postgresql_using="gin",
        postgresql_ops={"alias_text": "gin_trgm_ops"},
    )

    op.create_table(
        "users",
        sa.Column("tg_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("username", sa.String(32)),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("university_id", sa.Integer()),
        sa.Column("university_group", sa.String(50)),
        sa.Column("birth_date", sa.Date()),
        sa.Column("current_role", user_role, nullable=False, server_default="user"),
        sa.Column("role_before_ban", user_role),
        sa.Column("custom_permissions", postgresql.JSONB()),
        sa.Column("banned_at", sa.DateTime(timezone=True)),
        sa.Column("banned_reason", sa.Text()),
        sa.Column(
            "registration_date", sa.DateTime(timezone=True), nullable=False, server_default=NOW
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.ForeignKeyConstraint(
            ["university_id"],
            ["universities.university_id"],
            name="fk_users_university_id_universities",
        ),
    )
    op.create_index("ix_users_username", "users", ["username"])

    op.create_table(
        "registration_requests",
        sa.Column("request_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tg_id", sa.BigInteger(), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("university_id", sa.Integer(), nullable=False),
        sa.Column("university_group", sa.String(50), nullable=False),
        sa.Column("birth_date", sa.Date(), nullable=False),
        sa.Column("raw_input_snapshot", postgresql.JSONB()),
        sa.Column("status", request_status, nullable=False, server_default="pending"),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("next_allowed_attempt", sa.DateTime(timezone=True)),
        sa.Column("processed_by", sa.BigInteger()),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("admin_comment", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.ForeignKeyConstraint(
            ["university_id"],
            ["universities.university_id"],
            name="fk_registration_requests_university_id_universities",
        ),
        sa.ForeignKeyConstraint(
            ["processed_by"], ["users.tg_id"], name="fk_registration_requests_processed_by_users"
        ),
    )
    op.create_index("ix_registration_requests_tg_id", "registration_requests", ["tg_id"])
    op.create_index("ix_registration_requests_status", "registration_requests", ["status"])
    op.create_index(
        "ix_registration_requests_tg_id_status", "registration_requests", ["tg_id", "status"]
    )

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

    op.create_table(
        "audit_log",
        sa.Column("log_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("actor_tg_id", sa.BigInteger()),
        sa.Column("actor_type", actor_type, nullable=False, server_default="admin"),
        sa.Column("action_type", sa.String(50), nullable=False),
        sa.Column("target_tg_id", sa.BigInteger()),
        sa.Column("target_entity_type", sa.String(30)),
        sa.Column("target_entity_id", sa.String(64)),
        sa.Column("reason", sa.Text()),
        sa.Column("metadata", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.ForeignKeyConstraint(
            ["actor_tg_id"], ["users.tg_id"], name="fk_audit_log_actor_tg_id_users"
        ),
    )
    op.create_index("ix_audit_log_actor_tg_id", "audit_log", ["actor_tg_id"])
    op.create_index("ix_audit_log_action_type", "audit_log", ["action_type"])
    op.create_index("ix_audit_log_target_tg_id", "audit_log", ["target_tg_id"])
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_table("audit_log")
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
    op.drop_table("registration_requests")
    op.drop_table("users")
    op.drop_table("university_aliases")
    op.drop_table("universities")
    for enum in ALL_ENUMS:
        enum.drop(bind, checkfirst=True)
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
