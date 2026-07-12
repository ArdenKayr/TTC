import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import AliasSuggestion
from bot.enums import RequestStatus


async def get(session: AsyncSession, suggestion_id: uuid.UUID) -> AliasSuggestion | None:
    return await session.get(AliasSuggestion, suggestion_id)


async def count_for_user(session: AsyncSession, tg_id: int, university_id: int) -> int:
    """Сколько вариантов этот человек уже предложил этому вузу (любой статус)."""
    result = await session.execute(
        select(func.count()).where(
            AliasSuggestion.tg_id == tg_id,
            AliasSuggestion.university_id == university_id,
        )
    )
    return result.scalar_one()


async def try_mark_processed(
    session: AsyncSession,
    suggestion_id: uuid.UUID,
    new_status: RequestStatus,
    admin_tg_id: int,
    processed_at: datetime,
) -> bool:
    """Atomically claim a pending suggestion; False means another admin got there first."""
    result = await session.execute(
        update(AliasSuggestion)
        .where(
            AliasSuggestion.suggestion_id == suggestion_id,
            AliasSuggestion.status == RequestStatus.PENDING,
        )
        .values(status=new_status, processed_by=admin_tg_id, processed_at=processed_at)
    )
    return result.rowcount > 0


async def update_pending_text(
    session: AsyncSession, suggestion_id: uuid.UUID, alias_text: str
) -> bool:
    """Правка админом; False — предложение уже обработано."""
    result = await session.execute(
        update(AliasSuggestion)
        .where(
            AliasSuggestion.suggestion_id == suggestion_id,
            AliasSuggestion.status == RequestStatus.PENDING,
        )
        .values(alias_text=alias_text)
    )
    return result.rowcount > 0
