"""что нужно, чтобы мероприятие состоялось

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-03

В анкете мероприятия появился обязательный шаг: организатор пишет, что нужно
для проведения — люди, деньги, помещение, реквизит. Свободным текстом, потому
что заранее не угадать, что понадобится: одному нужны 15 человек и зал,
другому 100 000 ₽, третьему три помощника с реквизитом.

Колонка заведена необязательной: у заявок и мероприятий, поданных до этого
шага, такого поля не было, и придумывать за них «что нужно» неправильно —
в карточке строка просто не показывается.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("activity_requests", sa.Column("needs_text", sa.Text(), nullable=True))
    op.add_column("activities", sa.Column("needs_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("activities", "needs_text")
    op.drop_column("activity_requests", "needs_text")
