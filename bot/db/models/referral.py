from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from bot.db.base import Base


class ReferralLink(Base):
    """Именная ссылка-приглашение: по ней видно, кого привёл этот человек.

    Код ссылки уезжает в обычную ссылку на бота (`t.me/бот?start=код`), поэтому
    он короткий и без похожих друг на друга букв: его диктуют голосом и
    переписывают руками.

    Название — для самого админа: «Физфак», «Осенний набор». Ссылок у одного
    человека может быть несколько, и без названия он через месяц не вспомнит,
    какая откуда.
    """

    __tablename__ = "referral_links"

    code: Mapped[str] = mapped_column(sa.String(32), primary_key=True)
    # Чью работу считает ссылка. Удалил человек аккаунт — ссылка остаётся
    # ничьей, но со своими цифрами: сколько людей он привёл, из истории
    # сообщества не вычёркивается, как не вычёркиваются его заявки и репорты.
    owner_tg_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("users.tg_id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(sa.String(60))
    # Кто завёл ссылку: владелец раздаёт их админам, и потом бывает нужно
    # вспомнить, чья это была затея.
    created_by: Mapped[int | None] = mapped_column(
        sa.ForeignKey("users.tg_id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class ReferralVisit(Base):
    """Один человек, пришедший в бота по ссылке, и то, докуда он дошёл.

    Ключ — сам человек, а не пара «человек и ссылка». Это и есть правило
    «первого касания»: кто привёл человека в бота, тому он и засчитан, даже
    если потом тот откроет ещё три чужие ссылки. Иначе один и тот же новичок
    считался бы победой сразу у всех, кто скинул ему ссылку.

    Две отметки времени вместо одной: дойти до анкеты и попасть в сообщество —
    разные вещи. Ссылка, по которой заходят сотнями, а анкету подают трое,
    говорит о себе сама.
    """

    __tablename__ = "referral_visits"

    tg_id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=False)
    code: Mapped[str] = mapped_column(
        sa.ForeignKey("referral_links.code", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    # Заполняется, когда человек отправил анкету, и когда её приняли.
    applied_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
