from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot import texts
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
                await event.answer(texts.BANNED_ALERT, show_alert=True)
            elif isinstance(event, Message) and event.chat.type == ChatType.PRIVATE:
                # Текст редактируется в «Сценариях» (banned_guard); импорт локальный,
                # чтобы не циклиться с сервисами, которые тянут middleware-стек.
                from bot.services import scenario_service

                session = data.get("session")
                if session is not None:
                    content = await scenario_service.render(session, "banned_guard")
                    await event.answer(content.text)
                else:
                    await event.answer(texts.BANNED_DM)
            return None
        return await handler(event, data)
