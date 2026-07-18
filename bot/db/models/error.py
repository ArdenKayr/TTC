from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from bot.db.base import Base


class ErrorLog(Base):
    """Каждая необработанная ошибка хендлера: строка здесь + карточка владельцу в ЛС."""

    __tablename__ = "error_log"

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()"), index=True
    )
    update_type: Mapped[str | None] = mapped_column(sa.String(32))
    user_tg_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    chat_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    input_text: Mapped[str | None] = mapped_column(sa.Text)
    exception_type: Mapped[str] = mapped_column(sa.String(255))
    exception_message: Mapped[str] = mapped_column(sa.Text)
    traceback_text: Mapped[str] = mapped_column("traceback", sa.Text)
