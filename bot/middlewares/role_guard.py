from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.db.repositories import user_repo


class UserLoaderMiddleware(BaseMiddleware):
    """Loads the DB user (with role) into handler data as `db_user`."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        db_user = None
        from_user = getattr(event, "from_user", None)
        if from_user is not None:
            session = data["session"]
            db_user = await user_repo.get_by_tg_id(session, from_user.id)
            if db_user is not None and db_user.username != from_user.username:
                db_user.username = from_user.username
                await session.commit()
        data["db_user"] = db_user
        return await handler(event, data)
