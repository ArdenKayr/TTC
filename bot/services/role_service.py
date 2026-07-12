from datetime import datetime, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.config import settings
from bot.db.models import User
from bot.db.repositories import audit_repo
from bot.enums import AuditAction, UserRole

ASSIGNABLE_ROLES = {UserRole.USER, UserRole.ORGANIZER, UserRole.ADMIN, UserRole.CUSTOM}


async def set_role(
    session: AsyncSession, actor: User, target: User, new_role: UserRole
) -> str | None:
    """Returns a user-facing error, or None on success."""
    if new_role not in ASSIGNABLE_ROLES:
        return texts.ROLE_NOT_ASSIGNABLE
    if target.current_role == UserRole.BANNED:
        return texts.ROLE_TARGET_BANNED
    if target.current_role == new_role:
        return texts.ROLE_ALREADY_SET.format(role=new_role.value)
    old_role = target.current_role
    target.current_role = new_role
    await audit_repo.add(
        session,
        AuditAction.ROLE_CHANGED,
        actor_tg_id=actor.tg_id,
        target_tg_id=target.tg_id,
        target_entity_type="user",
        target_entity_id=str(target.tg_id),
        meta={"old_role": old_role.value, "new_role": new_role.value},
    )
    await session.commit()
    return None


async def ban_user(
    session: AsyncSession, bot: Bot, actor: User, target: User, reason: str | None
) -> str | None:
    if target.current_role == UserRole.BANNED:
        return texts.BAN_ALREADY
    target.role_before_ban = target.current_role
    target.current_role = UserRole.BANNED
    target.banned_at = datetime.now(timezone.utc)
    target.banned_reason = reason
    if settings.group_chat_id is not None:
        try:
            await bot.ban_chat_member(settings.group_chat_id, target.tg_id)
        except TelegramAPIError:
            pass
    await audit_repo.add(
        session,
        AuditAction.USER_BANNED,
        actor_tg_id=actor.tg_id,
        target_tg_id=target.tg_id,
        target_entity_type="user",
        target_entity_id=str(target.tg_id),
        reason=reason,
    )
    await session.commit()
    return None


async def unban_user(session: AsyncSession, bot: Bot, actor: User, target: User) -> str | None:
    if target.current_role != UserRole.BANNED:
        return texts.UNBAN_NOT_BANNED
    restored = target.role_before_ban or UserRole.USER
    target.current_role = restored
    target.role_before_ban = None
    target.banned_at = None
    target.banned_reason = None
    if settings.group_chat_id is not None:
        try:
            await bot.unban_chat_member(settings.group_chat_id, target.tg_id, only_if_banned=True)
        except TelegramAPIError:
            pass
    await audit_repo.add(
        session,
        AuditAction.USER_UNBANNED,
        actor_tg_id=actor.tg_id,
        target_tg_id=target.tg_id,
        target_entity_type="user",
        target_entity_id=str(target.tg_id),
        meta={"restored_role": restored.value},
    )
    await session.commit()
    return None
