"""репорты: статус, номер и переписка с автором

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-04

Репорт был разовым сообщением в чат админов: разобрать его можно было только
сразу, а автор никогда не узнавал, чем дело кончилось. Теперь это запись,
к которой возвращаются: у неё есть номер (его называют человеку), статус
и ветка переписки.

Ссылки на автора обнуляются при удалении человека (как в миграции 0011):
репорт остаётся в работе, даже если тот, кто его прислал, ушёл из сообщества.
Имя автора продублировано строкой — иначе после удаления карточка стала бы
жалобой неизвестно от кого. Переписка привязана к репорту жёстко: удалили
репорт — ветка уходит вместе с ним, отдельно она бессмысленна.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

report_status = postgresql.ENUM(
    "new", "in_progress", "done", "declined", name="report_status", create_type=False
)


def upgrade() -> None:
    report_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "reports",
        sa.Column("report_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "author_tg_id",
            sa.BigInteger(),
            sa.ForeignKey("users.tg_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("author_name", sa.String(255), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", report_status, nullable=False, server_default="new"),
        sa.Column(
            "taken_by",
            sa.BigInteger(),
            sa.ForeignKey("users.tg_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("card_message_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    )
    op.create_index("ix_reports_author_tg_id", "reports", ["author_tg_id"])
    op.create_index("ix_reports_status", "reports", ["status"])

    op.create_table(
        "report_messages",
        sa.Column("message_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "report_id",
            sa.Integer(),
            sa.ForeignKey("reports.report_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_admin", sa.Boolean(), nullable=False),
        sa.Column(
            "author_tg_id",
            sa.BigInteger(),
            sa.ForeignKey("users.tg_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("author_name", sa.String(255), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    )
    op.create_index("ix_report_messages_report_id", "report_messages", ["report_id"])


def downgrade() -> None:
    op.drop_table("report_messages")
    op.drop_table("reports")
    report_status.drop(op.get_bind(), checkfirst=True)
