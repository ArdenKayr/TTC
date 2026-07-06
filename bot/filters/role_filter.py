from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject

from bot.db.models import User
from bot.enums import UserRole


class IsAdmin(BaseFilter):
    async def __call__(self, event: TelegramObject, db_user: User | None = None) -> bool:
        return db_user is not None and db_user.current_role == UserRole.ADMIN


class IsOrganizerOrAbove(BaseFilter):
    async def __call__(self, event: TelegramObject, db_user: User | None = None) -> bool:
        return db_user is not None and db_user.current_role in (
            UserRole.ORGANIZER,
            UserRole.ADMIN,
        )
