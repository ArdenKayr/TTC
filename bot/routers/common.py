from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

from bot.db.models import User
from bot.enums import UserRole
from bot.services import notification_service

router = Router(name="common")

ROLE_LABELS = {
    UserRole.USER: "Пользователь",
    UserRole.ORGANIZER: "Организатор",
    UserRole.ADMIN: "Админ",
    UserRole.CUSTOM: "Кастомная роль",
}


@router.message(CommandStart(), F.chat.type == ChatType.PRIVATE)
async def cmd_start(message: Message, db_user: User | None) -> None:
    if db_user is None:
        await message.answer(
            "👋 Привет! Это бот студенческого сообщества.\n\n"
            "Чтобы вступить, подайте заявку на регистрацию: /register"
        )
        return
    role = ROLE_LABELS.get(db_user.current_role, db_user.current_role.value)
    await message.answer(f"С возвращением, {db_user.display_name}!\nВаша роль: {role}.")


@router.message(Command("report"), F.chat.type == ChatType.PRIVATE)
async def cmd_report(message: Message, command: CommandObject, db_user: User | None) -> None:
    if db_user is None:
        await message.answer("Репорты доступны после регистрации: /register")
        return
    text = (command.args or "").strip()
    if not text:
        await message.answer("Использование: /report <описание проблемы или бага>")
        return
    username = f"@{db_user.username}" if db_user.username else f"id {db_user.tg_id}"
    await notification_service.send_admin_report(
        message.bot, f"🐞 Репорт от {db_user.display_name} ({username}):\n\n{text}"
    )
    await message.answer("Спасибо! Репорт отправлен админам.")
