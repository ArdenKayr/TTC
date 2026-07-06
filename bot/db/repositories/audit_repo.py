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
