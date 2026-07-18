"""extended activity form fields (Bot 2.0 block B)

The activity request now collects organizers (text with tg links), an
implementation-plan link, an activity-chat link and an optional comment
for admins; the single extra_url column is replaced by these.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-18

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("activity_requests", sa.Column("organizers_text", sa.Text(), nullable=True))
    op.add_column("activity_requests", sa.Column("plan_url", sa.String(512), nullable=True))
    op.add_column("activity_requests", sa.Column("chat_url", sa.String(512), nullable=True))
    op.add_column("activity_requests", sa.Column("admin_comment", sa.Text(), nullable=True))
    op.drop_column("activity_requests", "extra_url")

    op.add_column("activities", sa.Column("organizers_text", sa.Text(), nullable=True))
    op.add_column("activities", sa.Column("plan_url", sa.String(512), nullable=True))
    op.add_column("activities", sa.Column("chat_url", sa.String(512), nullable=True))
    op.drop_column("activities", "extra_url")


def downgrade() -> None:
    op.add_column("activities", sa.Column("extra_url", sa.String(512), nullable=True))
    op.drop_column("activities", "chat_url")
    op.drop_column("activities", "plan_url")
    op.drop_column("activities", "organizers_text")

    op.add_column("activity_requests", sa.Column("extra_url", sa.String(512), nullable=True))
    op.drop_column("activity_requests", "admin_comment")
    op.drop_column("activity_requests", "chat_url")
    op.drop_column("activity_requests", "plan_url")
    op.drop_column("activity_requests", "organizers_text")
