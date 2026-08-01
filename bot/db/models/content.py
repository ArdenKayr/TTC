from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from bot.db.base import Base


class ContentBlock(Base):
    """Admin-editable content shown to users; valid slot keys are defined in code."""

    __tablename__ = "content_blocks"

    slot: Mapped[str] = mapped_column(sa.String(50), primary_key=True)
    text: Mapped[str | None] = mapped_column(sa.Text)
    file_id: Mapped[str | None] = mapped_column(sa.String(255))
    file_type: Mapped[str | None] = mapped_column(sa.String(20))
    updated_by: Mapped[int | None] = mapped_column(
        sa.ForeignKey("users.tg_id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()"), onupdate=sa.func.now()
    )
