from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.db.models import User
from bot.db.repositories import user_repo
from bot.enums import PermissionModule, UserRole
from bot.filters.role_filter import HasPerm, IsSuperadmin
from bot.services import role_service, scenario_service

router = Router(name="admin_moderation")


async def _resolve_target(session: AsyncSession, ref: str) -> User | None:
    if ref.lstrip("-").isdigit():
        return await user_repo.get_by_tg_id(session, int(ref))
    return await user_repo.get_by_username(session, ref)


@router.message(Command("ban"), HasPerm(PermissionModule.MODERATION))
async def cmd_ban(
    message: Message, command: CommandObject, session: AsyncSession, db_user: User
) -> None:
    args = (command.args or "").split(maxsplit=1)
    if not args:
        await message.answer(texts.BAN_USAGE)
        return
    target = await _resolve_target(session, args[0])
    if target is None:
        await message.answer(texts.USER_NOT_FOUND)
        return
    if target.tg_id == db_user.tg_id:
        await message.answer(texts.BAN_SELF)
        return
    reason = args[1] if len(args) > 1 else None
    error = await role_service.ban_user(session, message.bot, db_user, target, reason)
    if error:
        await message.answer(error)
        return
    await scenario_service.reply(
        message, session, "ban_done", name=target.display_name, tg_id=target.tg_id
    )


@router.message(Command("unban"), HasPerm(PermissionModule.MODERATION))
async def cmd_unban(
    message: Message, command: CommandObject, session: AsyncSession, db_user: User
) -> None:
    ref = (command.args or "").strip()
    if not ref:
        await message.answer(texts.UNBAN_USAGE)
        return
    target = await _resolve_target(session, ref)
    if target is None:
        await message.answer(texts.USER_NOT_FOUND)
        return
    error = await role_service.unban_user(session, message.bot, db_user, target)
    if error:
        await message.answer(error)
        return
    await message.answer(
        texts.UNBAN_DONE.format(name=target.display_name, role=target.current_role.value)
    )


# Роли: суперадмин назначает до админа, владелец — до суперадмина,
# простые админы роли не раздают (иерархия проверяется и в сервисе).
@router.message(Command("setrole"), IsSuperadmin())
async def cmd_setrole(
    message: Message, command: CommandObject, session: AsyncSession, db_user: User
) -> None:
    args = (command.args or "").split()
    valid_roles = ", ".join(sorted(r.value for r in role_service.assignable_roles(db_user)))
    if len(args) != 2:
        await message.answer(texts.SETROLE_USAGE.format(roles=valid_roles))
        return
    try:
        new_role = UserRole(args[1].lower())
    except ValueError:
        await message.answer(texts.SETROLE_UNKNOWN.format(roles=valid_roles))
        return
    target = await _resolve_target(session, args[0])
    if target is None:
        await message.answer(texts.USER_NOT_FOUND)
        return
    error = await role_service.set_role(session, db_user, target, new_role)
    if error:
        await message.answer(error)
        return
    await message.answer(
        texts.SETROLE_DONE.format(name=target.display_name, role=new_role.value)
    )
