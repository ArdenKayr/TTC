"""university requests, alias suggestions, nick-based registration

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-13

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

request_status = postgresql.ENUM(
    "pending", "approved", "rejected", name="request_status", create_type=False
)
NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "university_requests",
        sa.Column("request_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tg_id", sa.BigInteger(), nullable=False),
        sa.Column("applicant_name", sa.String(255), nullable=False),
        sa.Column("applicant_username", sa.String(32)),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "aliases", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("link", sa.String(512), nullable=False),
        sa.Column("status", request_status, nullable=False, server_default="pending"),
        sa.Column("processed_by", sa.BigInteger()),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("admin_comment", sa.Text()),
        sa.Column("created_university_id", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.ForeignKeyConstraint(
            ["processed_by"], ["users.tg_id"], name="fk_university_requests_processed_by_users"
        ),
        sa.ForeignKeyConstraint(
            ["created_university_id"],
            ["universities.university_id"],
            name="fk_university_requests_created_university",
        ),
    )
    op.create_index("ix_university_requests_tg_id", "university_requests", ["tg_id"])
    op.create_index("ix_university_requests_status", "university_requests", ["status"])

    op.create_table(
        "alias_suggestions",
        sa.Column("suggestion_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("university_id", sa.Integer(), nullable=False),
        sa.Column("tg_id", sa.BigInteger(), nullable=False),
        sa.Column("applicant_name", sa.String(255), nullable=False),
        sa.Column("applicant_username", sa.String(32)),
        sa.Column("alias_text", sa.String(255), nullable=False),
        sa.Column("status", request_status, nullable=False, server_default="pending"),
        sa.Column("processed_by", sa.BigInteger()),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.ForeignKeyConstraint(
            ["university_id"],
            ["universities.university_id"],
            name="fk_alias_suggestions_university_id_universities",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["processed_by"], ["users.tg_id"], name="fk_alias_suggestions_processed_by_users"
        ),
    )
    op.create_index(
        "ix_alias_suggestions_tg_id_university_id",
        "alias_suggestions",
        ["tg_id", "university_id"],
    )
    op.create_index("ix_alias_suggestions_status", "alias_suggestions", ["status"])

    op.alter_column(
        "registration_requests", "university_id", existing_type=sa.Integer(), nullable=True
    )
    op.alter_column(
        "registration_requests", "university_group", existing_type=sa.String(50), nullable=True
    )
    op.add_column("registration_requests", sa.Column("about_text", sa.Text()))
    op.add_column(
        "registration_requests",
        sa.Column("university_request_id", postgresql.UUID(as_uuid=True)),
    )
    op.create_foreign_key(
        "fk_reg_requests_university_request",
        "registration_requests",
        "university_requests",
        ["university_request_id"],
        ["request_id"],
    )

    op.add_column("users", sa.Column("about_text", sa.Text()))


def downgrade() -> None:
    op.drop_column("users", "about_text")
    op.drop_constraint(
        "fk_reg_requests_university_request", "registration_requests", type_="foreignkey"
    )
    op.drop_column("registration_requests", "university_request_id")
    op.drop_column("registration_requests", "about_text")
    op.alter_column(
        "registration_requests", "university_group", existing_type=sa.String(50), nullable=False
    )
    op.alter_column(
        "registration_requests", "university_id", existing_type=sa.Integer(), nullable=False
    )
    op.drop_index("ix_alias_suggestions_status", table_name="alias_suggestions")
    op.drop_index("ix_alias_suggestions_tg_id_university_id", table_name="alias_suggestions")
    op.drop_table("alias_suggestions")
    op.drop_index("ix_university_requests_status", table_name="university_requests")
    op.drop_index("ix_university_requests_tg_id", table_name="university_requests")
    op.drop_table("university_requests")
