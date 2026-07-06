from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User
from bot.db.repositories import user_repo
from bot.enums import UserRole
from bot.filters.role_filter import IsAdmin
from bot.services import role_service

router = Router(name="admin_moderation")
router.message.filter(IsAdmin())


async def _resolve_target(session: AsyncSession, ref: str) -> User | None:
    if ref.lstrip("-").isdigit():
        return await user_repo.get_by_tg_id(session, int(ref))
    return await user_repo.get_by_username(session, ref)


@router.message(Command("ban"))
async def cmd_ban(
    message: Message, command: CommandObject, session: AsyncSession, db_user: User
) -> None:
    args = (command.args or "").split(maxsplit=1)
    if not args:
        await message.answer("Использование: /ban <tg_id | @username> [причина]")
        return
    target = await _resolve_target(session, args[0])
    if target is None:
        await message.answer("Пользователь не найден в базе.")
        return
    if target.tg_id == db_user.tg_id:
        await message.answer("Нельзя забанить самого себя.")
        return
    reason = args[1] if len(args) > 1 else None
    error = await role_service.ban_user(session, message.bot, db_user, target, reason)
    if error:
        await message.answer(error)
        return
    await message.answer(f"🔨 {target.display_name} (id {target.tg_id}) забанен.")


@router.message(Command("unban"))
async def cmd_unban(
    message: Message, command: CommandObject, session: AsyncSession, db_user: User
) -> None:
    ref = (command.args or "").strip()
    if not ref:
        await message.answer("Использование: /unban <tg_id | @username>")
        return
    target = await _resolve_target(session, ref)
    if target is None:
        await message.answer("Пользователь не найден в базе.")
        return
    error = await role_service.unban_user(session, message.bot, db_user, target)
    if error:
        await message.answer(error)
        return
    await message.answer(
        f"✅ {target.display_name} разбанен, роль восстановлена: {target.current_role.value}."
    )


@router.message(Command("setrole"))
async def cmd_setrole(
    message: Message, command: CommandObject, session: AsyncSession, db_user: User
) -> None:
    args = (command.args or "").split()
    valid_roles = ", ".join(r.value for r in role_service.ASSIGNABLE_ROLES)
    if len(args) != 2:
        await message.answer(f"Использование: /setrole <tg_id | @username> <{valid_roles}>")
        return
    try:
        new_role = UserRole(args[1].lower())
    except ValueError:
        await message.answer(f"Неизвестная роль. Доступные: {valid_roles}")
        return
    target = await _resolve_target(session, args[0])
    if target is None:
        await message.answer("Пользователь не найден в базе.")
        return
    error = await role_service.set_role(session, db_user, target, new_role)
    if error:
        await message.answer(error)
        return
    await message.answer(f"✅ Роль {target.display_name} изменена на {new_role.value}.")
