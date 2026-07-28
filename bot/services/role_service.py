from datetime import datetime, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.config import settings
from bot.db.models import User
from bot.db.repositories import audit_repo
from bot.keyboards.common_kb import main_menu_kb
from bot.enums import AuditAction, UserRole, role_rank
from bot.services import error_service, scenario_service

# Иерархия назначений: простые админы роли не раздают, суперадмин назначает
# до админа включительно, владелец — до суперадмина. Роль «владелец» не
# назначается через бота вообще (только bootstrap-скриптом с сервера).
_BASE_ASSIGNABLE = {UserRole.USER, UserRole.ORGANIZER, UserRole.ADMIN, UserRole.CUSTOM}


def assignable_roles(actor: User) -> set[UserRole]:
    if actor.current_role == UserRole.OWNER:
        return _BASE_ASSIGNABLE | {UserRole.SUPERADMIN}
    if actor.current_role == UserRole.SUPERADMIN:
        return _BASE_ASSIGNABLE
    return set()


async def set_role(
    session: AsyncSession, actor: User, target: User, new_role: UserRole
) -> str | None:
    """Returns a user-facing error, or None on success."""
    allowed = assignable_roles(actor)
    if not allowed:
        return texts.ROLE_NO_RIGHTS
    if new_role not in allowed:
        return texts.ROLE_NOT_ASSIGNABLE
    # Нельзя менять роль тому, кто в иерархии не ниже тебя (кроме самого себя):
    # суперадмин не трогает суперадминов и владельца, владельца не трогает никто.
    if target.tg_id != actor.tg_id and role_rank(target.current_role) >= role_rank(
        actor.current_role
    ):
        return texts.ROLE_TARGET_PROTECTED
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
    # Банить админов может только тот, кто выше их по иерархии:
    # админа — суперадмин или владелец, суперадмина — владелец, владельца — никто.
    if role_rank(target.current_role) > 0 and role_rank(target.current_role) >= role_rank(
        actor.current_role
    ):
        return texts.BAN_TARGET_PROTECTED
    target.role_before_ban = target.current_role
    target.current_role = UserRole.BANNED
    target.banned_at = datetime.now(timezone.utc)
    target.banned_reason = reason
    if settings.group_chat_id is not None:
        try:
            await bot.ban_chat_member(settings.group_chat_id, target.tg_id)
        except TelegramAPIError as e:
            # Роль в базе уже «забанен», а физически человек мог остаться в группе —
            # это должно быть видно, а не тонуть молча.
            await error_service.report_issue(
                bot,
                source="Бан",
                tg_id=target.tg_id,
                note=f"Роль сменена на «забанен», но исключить из группы не удалось: {e}",
            )
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
    # Цель узнаёт о бане в ЛС (текст редактируется в «Сценариях»); заодно
    # убираем меню — все его кнопки для забаненного всё равно не работают.
    await scenario_service.dm(
        bot, session, target.tg_id, "ban_target", reply_markup=ReplyKeyboardRemove()
    )
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
        except TelegramAPIError as e:
            await error_service.report_issue(
                bot,
                source="Разбан",
                tg_id=target.tg_id,
                note=f"Роль восстановлена в базе, но снять ограничения в группе не удалось: {e}",
            )
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
    # Меню возвращается сразу — под ту роль, которая восстановлена.
    await scenario_service.dm(
        bot, session, target.tg_id, "unban_target", reply_markup=main_menu_kb(target)
    )
    return None
