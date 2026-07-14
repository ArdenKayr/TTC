"""permission groups (admin permission modules)

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-14

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "permission_groups",
        sa.Column("group_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column(
            "modules", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("name", name="uq_permission_groups_name"),
    )
    op.add_column("users", sa.Column("permission_group_id", sa.Integer()))
    op.create_foreign_key(
        "fk_users_permission_group",
        "users",
        "permission_groups",
        ["permission_group_id"],
        ["group_id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_permission_group", "users", type_="foreignkey")
    op.drop_column("users", "permission_group_id")
    op.drop_table("permission_groups")
