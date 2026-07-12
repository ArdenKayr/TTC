"""content blocks

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-12

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_blocks",
        sa.Column("slot", sa.String(50), primary_key=True),
        sa.Column("text", sa.Text()),
        sa.Column("file_id", sa.String(255)),
        sa.Column("file_type", sa.String(20)),
        sa.Column("updated_by", sa.BigInteger()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.tg_id"], name="fk_content_blocks_updated_by_users"
        ),
    )


def downgrade() -> None:
    op.drop_table("content_blocks")
