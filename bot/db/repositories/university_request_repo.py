import uuid
from datetime import datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import UniversityRequest
from bot.enums import RequestStatus


async def get(session: AsyncSession, request_id: uuid.UUID) -> UniversityRequest | None:
    return await session.get(UniversityRequest, request_id)


async def try_mark_processed(
    session: AsyncSession,
    request_id: uuid.UUID,
    new_status: RequestStatus,
    admin_tg_id: int,
    processed_at: datetime,
) -> bool:
    """Atomically claim a pending request; False means another admin got there first."""
    result = await session.execute(
        update(UniversityRequest)
        .where(
            UniversityRequest.request_id == request_id,
            UniversityRequest.status == RequestStatus.PENDING,
        )
        .values(status=new_status, processed_by=admin_tg_id, processed_at=processed_at)
    )
    return result.rowcount > 0


async def update_pending_data(
    session: AsyncSession, request_id: uuid.UUID, name: str, aliases: list[str]
) -> bool:
    """Правка админом; False — заявка уже обработана, менять поздно."""
    result = await session.execute(
        update(UniversityRequest)
        .where(
            UniversityRequest.request_id == request_id,
            UniversityRequest.status == RequestStatus.PENDING,
        )
        .values(name=name, aliases=aliases)
    )
    return result.rowcount > 0
