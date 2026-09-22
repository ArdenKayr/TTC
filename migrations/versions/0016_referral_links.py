"""ссылки-приглашения и счёт переходов по ним

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-22

Сообщество растёт руками админов, но до сих пор было не видно, чьими именно:
новичок приходил «сам по себе», и разговор о том, кто сколько привёл, упирался
в ощущения. Теперь у админа есть именная ссылка на бота, а у ссылки — счётчик.

Две таблицы. В первой — сами ссылки: код, владелец, человеческое название.
Во второй — люди, пришедшие по ним, по одной строке на человека: ключ там сам
tg_id, и это правило «первого касания». Кто привёл человека в бота, тому он и
засчитан; открытые потом чужие ссылки его уже не перепишут, иначе один новичок
числился бы победой у всех, кто скинул ему ссылку.

Владелец ссылки может исчезнуть: `owner_tg_id` обнуляется вместе с удалением
аккаунта, а ссылка остаётся со своими цифрами. Сколько человек привёл ушедший
админ — часть истории сообщества, как и его заявки с репортами.

Отметки `applied_at` и `approved_at` разделены нарочно: дойти до анкеты и
попасть в сообщество — разные вещи, и ссылка, по которой заходят сотнями, а
анкету подают трое, должна быть видна как есть.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "referral_links",
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("owner_tg_id", sa.BigInteger(), nullable=True),
        sa.Column("title", sa.String(length=60), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_referral_links")),
        sa.ForeignKeyConstraint(
            ["owner_tg_id"],
            ["users.tg_id"],
            name=op.f("fk_referral_links_owner_tg_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.tg_id"],
            name=op.f("fk_referral_links_created_by_users"),
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        op.f("ix_referral_links_owner_tg_id"), "referral_links", ["owner_tg_id"], unique=False
    )

    op.create_table(
        "referral_visits",
        sa.Column("tg_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("tg_id", name=op.f("pk_referral_visits")),
        sa.ForeignKeyConstraint(
            ["code"],
            ["referral_links.code"],
            name=op.f("fk_referral_visits_code_referral_links"),
            ondelete="CASCADE",
        ),
    )
    op.create_index(op.f("ix_referral_visits_code"), "referral_visits", ["code"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_referral_visits_code"), table_name="referral_visits")
    op.drop_table("referral_visits")
    op.drop_index(op.f("ix_referral_links_owner_tg_id"), table_name="referral_links")
    op.drop_table("referral_links")
