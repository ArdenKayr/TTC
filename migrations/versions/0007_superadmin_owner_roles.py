"""add superadmin and owner values to the user_role enum

Hierarchy: owner > superadmin > admin. Plain admins cannot assign roles,
superadmins assign admins, the owner assigns admins and superadmins.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-18

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'superadmin'")
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'owner'")


def downgrade() -> None:
    # Убрать значение из enum в PostgreSQL нельзя без пересоздания типа;
    # лишние значения безвредны, поэтому откат ничего не делает.
    pass
