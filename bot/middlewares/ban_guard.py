from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.enums import UserRole


class BanGuardMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        db_user = data.get("db_user")
        if db_user is not None and db_user.current_role == UserRole.BANNED:
            if isinstance(event, CallbackQuery):
                await event.answer("⛔ Доступ заблокирован.", show_alert=True)
            elif isinstance(event, Message) and event.chat.type == ChatType.PRIVATE:
                await event.answer("⛔ Доступ к боту заблокирован.")
            return None
        return await handler(event, data)
