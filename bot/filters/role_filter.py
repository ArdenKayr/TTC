from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User
from bot.enums import FULL_ADMIN_ROLES, PermissionModule, UserRole


class IsAdmin(BaseFilter):
    """Полные права на повседневные модули: админ, суперадмин или владелец."""

    async def __call__(self, event: TelegramObject, db_user: User | None = None) -> bool:
        return db_user is not None and db_user.current_role in FULL_ADMIN_ROLES


class IsSuperadmin(BaseFilter):
    """Панель суперадмина: суперадмин или владелец."""

    async def __call__(self, event: TelegramObject, db_user: User | None = None) -> bool:
        return db_user is not None and db_user.current_role in (
            UserRole.SUPERADMIN,
            UserRole.OWNER,
        )


class IsOwner(BaseFilter):
    async def __call__(self, event: TelegramObject, db_user: User | None = None) -> bool:
        return db_user is not None and db_user.current_role == UserRole.OWNER


class HasPerm(BaseFilter):
    """Пропускает полного админа и тех, кому модуль включён (группой или лично)."""

    def __init__(self, module: PermissionModule) -> None:
        self.module = module

    async def __call__(
        self,
        event: TelegramObject,
        db_user: User | None = None,
        session: AsyncSession | None = None,
    ) -> bool:
        if db_user is None or session is None:
            return False
        from bot.services import permission_service

        return await permission_service.has_permission(session, db_user, self.module)


class IsOrganizerOrAbove(BaseFilter):
    async def __call__(self, event: TelegramObject, db_user: User | None = None) -> bool:
        return db_user is not None and (
            db_user.current_role == UserRole.ORGANIZER
            or db_user.current_role in FULL_ADMIN_ROLES
        )
