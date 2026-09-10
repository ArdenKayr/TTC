"""переключатели бота, меняемые из панели

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-10

Появился автоприём заявок на вступление, и его надо уметь включать и выключать
на ходу. Держать такой рычаг в `.env` нельзя: смена значения там требует
доступа к серверу и перезапуска бота, а решение «пускать всех подходящих
самим» принимается в разгар наплыва, часто с телефона.

Поэтому отдельная маленькая таблица «ключ — значение». Значение строкой:
переключателей мало, они разнородные, и заводить под каждый свою колонку
значило бы ходить в миграции за каждой мелочью.

Таблица пустая: отсутствие ключа означает «выключено». Автоприём после
обновления не включается сам — это осознанное решение владельца, а не
поведение по умолчанию.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bot_settings",
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_bot_settings")),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.tg_id"],
            name=op.f("fk_bot_settings_updated_by_users"),
            ondelete="SET NULL",
        ),
    )


def downgrade() -> None:
    op.drop_table("bot_settings")
