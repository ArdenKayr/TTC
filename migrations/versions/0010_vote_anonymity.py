"""vote anonymity

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-19

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Раньше все опросы публиковались анонимными — у старых заявок оставляем это.
    op.add_column(
        "vote_requests",
        sa.Column(
            "is_anonymous", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
    )


def downgrade() -> None:
    op.drop_column("vote_requests", "is_anonymous")
