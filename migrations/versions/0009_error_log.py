"""error log

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-18

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "error_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("update_type", sa.String(32)),
        sa.Column("user_tg_id", sa.BigInteger()),
        sa.Column("chat_id", sa.BigInteger()),
        sa.Column("input_text", sa.Text()),
        sa.Column("exception_type", sa.String(255), nullable=False),
        sa.Column("exception_message", sa.Text(), nullable=False),
        sa.Column("traceback", sa.Text(), nullable=False),
    )
    op.create_index("ix_error_log_occurred_at", "error_log", ["occurred_at"])


def downgrade() -> None:
    op.drop_table("error_log")
