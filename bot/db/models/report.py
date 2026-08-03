from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from bot.db.base import Base
from bot.db.models._types import report_status_enum
from bot.enums import ReportStatus


class Report(Base):
    """Жалоба или предложение от участника — с номером, статусом и перепиской.

    Раньше репорт был одним сообщением в чат админов: разобрать его можно было
    только сразу, а автор никогда не узнавал, чем дело кончилось. Теперь это
    запись, к которой возвращаются.

    Номер — обычное целое, а не UUID, потому что его называют вслух и пишут
    человеку: «репорт №7» понятно, «репорт 4f3a…» — нет.
    """

    __tablename__ = "reports"

    report_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    author_tg_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("users.tg_id", ondelete="SET NULL"), index=True
    )
    # Снимок имени: автора могут удалить из базы, но карточка репорта должна
    # остаться читаемой — иначе админ видит жалобу неизвестно от кого.
    author_name: Mapped[str] = mapped_column(sa.String(255))
    text: Mapped[str] = mapped_column(sa.Text)
    status: Mapped[ReportStatus] = mapped_column(
        report_status_enum,
        default=ReportStatus.NEW,
        server_default=ReportStatus.NEW.value,
        index=True,
    )
    # Кто взял репорт в работу — чтобы за один не брались двое.
    taken_by: Mapped[int | None] = mapped_column(
        sa.ForeignKey("users.tg_id", ondelete="SET NULL")
    )
    # Карточка в админ-чате: её правим при каждой смене статуса, чтобы в чате
    # не копились устаревшие карточки с живыми кнопками.
    card_message_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class ReportMessage(Base):
    """Одно сообщение переписки по репорту — от админа автору или обратно.

    Хранится вся ветка: админ, открывший репорт через неделю, должен видеть,
    что автору уже отвечали и что он на это сказал.
    """

    __tablename__ = "report_messages"

    message_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(
        sa.ForeignKey("reports.report_id", ondelete="CASCADE"), index=True
    )
    # True — писал админ автору, False — автор отвечал админам.
    from_admin: Mapped[bool] = mapped_column(sa.Boolean)
    author_tg_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("users.tg_id", ondelete="SET NULL")
    )
    author_name: Mapped[str] = mapped_column(sa.String(255))
    text: Mapped[str] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
