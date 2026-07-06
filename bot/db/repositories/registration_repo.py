import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import RegistrationRequest
from bot.enums import RequestStatus


async def get(session: AsyncSession, request_id: uuid.UUID) -> RegistrationRequest | None:
    return await session.get(RegistrationRequest, request_id)


async def has_pending(session: AsyncSession, tg_id: int) -> bool:
    result = await session.execute(
        select(RegistrationRequest.request_id)
        .where(
            RegistrationRequest.tg_id == tg_id,
            RegistrationRequest.status == RequestStatus.PENDING,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def latest_next_allowed_attempt(session: AsyncSession, tg_id: int) -> datetime | None:
    result = await session.execute(
        select(RegistrationRequest.next_allowed_attempt)
        .where(RegistrationRequest.tg_id == tg_id)
        .order_by(RegistrationRequest.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def next_attempt_number(session: AsyncSession, tg_id: int) -> int:
    result = await session.execute(
        select(func.max(RegistrationRequest.attempt_number)).where(
            RegistrationRequest.tg_id == tg_id
        )
    )
    return (result.scalar_one() or 0) + 1


async def try_mark_processed(
    session: AsyncSession,
    request_id: uuid.UUID,
    new_status: RequestStatus,
    admin_tg_id: int,
    processed_at: datetime,
    next_allowed_attempt: datetime | None = None,
) -> bool:
    """Atomically claim a pending request; False means another admin got there first."""
    values: dict = {
        "status": new_status,
        "processed_by": admin_tg_id,
        "processed_at": processed_at,
    }
    if next_allowed_attempt is not None:
        values["next_allowed_attempt"] = next_allowed_attempt
    result = await session.execute(
        update(RegistrationRequest)
        .where(
            RegistrationRequest.request_id == request_id,
            RegistrationRequest.status == RequestStatus.PENDING,
        )
        .values(**values)
    )
    return result.rowcount > 0
