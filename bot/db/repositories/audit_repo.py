from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import AuditLog
from bot.enums import ActorType, AuditAction


async def add(
    session: AsyncSession,
    action: AuditAction,
    *,
    actor_tg_id: int | None = None,
    actor_type: ActorType = ActorType.ADMIN,
    target_tg_id: int | None = None,
    target_entity_type: str | None = None,
    target_entity_id: str | None = None,
    reason: str | None = None,
    meta: dict | None = None,
) -> None:
    session.add(
        AuditLog(
            actor_tg_id=actor_tg_id,
            actor_type=actor_type,
            action_type=action.value,
            target_tg_id=target_tg_id,
            target_entity_type=target_entity_type,
            target_entity_id=target_entity_id,
            reason=reason,
            meta=meta,
        )
    )


async def list_recent(
    session: AsyncSession,
    *,
    actions: Sequence[str] | None = None,
    since: datetime | None = None,
    limit: int = 25,
) -> tuple[list[AuditLog], int]:
    """Свежие записи по фильтру (для панели «Логи») + сколько их всего."""
    query = select(AuditLog)
    if actions is not None:
        query = query.where(AuditLog.action_type.in_(actions))
    if since is not None:
        query = query.where(AuditLog.created_at >= since)
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = await session.scalars(query.order_by(AuditLog.created_at.desc()).limit(limit))
    return list(rows), total
