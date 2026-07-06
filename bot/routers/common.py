from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.db.models import User
from bot.enums import UserRole

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
