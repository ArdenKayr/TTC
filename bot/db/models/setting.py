from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from bot.db.base import Base


class BotSetting(Base):
    """Переключатели, которые владелец меняет на ходу — из панели, не выкаткой.

    Настройки бота живут в двух местах, и это разделение намеренное. В `.env`
    лежит то, что описывает саму установку: токен, номера чатов, адрес базы.
    Меняется это редко, требует доступа к серверу и перезапуска — и правильно,
    что требует.

    Здесь — то, что владелец решает по ходу жизни сообщества и может захотеть
    переключить в любую минуту, в том числе с телефона и в разгар наплыва.
    Первый такой переключатель — автоприём заявок на вступление.

    Значение хранится строкой: переключателей мало, они разнородные, и заводить
    под каждый свою колонку значило бы ходить в миграции за каждой мелочью.
    """

    __tablename__ = "bot_settings"

    key: Mapped[str] = mapped_column(sa.String(50), primary_key=True)
    value: Mapped[str] = mapped_column(sa.String(255))
    updated_by: Mapped[int | None] = mapped_column(
        sa.ForeignKey("users.tg_id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()"), onupdate=sa.func.now()
    )
