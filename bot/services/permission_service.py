"""Модули админских прав.

Каждый модуль — независимый кусок функционала бота. Модули включаются
одной кнопкой: либо группе прав (и тогда действуют на всех её участников),
либо лично человеку. Полный админ (роль admin) может всё без всяких групп;
управлять группами и правами может только полный админ.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import PermissionGroup, User
from bot.db.repositories import audit_repo, permission_repo
from bot.enums import FULL_ADMIN_ROLES, AuditAction, PermissionModule, UserRole


@dataclass(frozen=True)
class Module:
    key: str
    title: str


# Реестр модулей: новый модуль = строка здесь + значение в PermissionModule
# + фильтр HasPerm(...) на соответствующем роутере.
MODULES: dict[str, Module] = {
    PermissionModule.REGISTRATION.value: Module(
        PermissionModule.REGISTRATION.value, "Заявки на регистрацию"
    ),
    PermissionModule.UNIVERSITIES.value: Module(
        PermissionModule.UNIVERSITIES.value, "Вузы и варианты поиска"
    ),
    PermissionModule.CONTENT.value: Module(
        PermissionModule.CONTENT.value, "Тексты и файлы бота («📄 Разделы»)"
    ),
    PermissionModule.MODERATION.value: Module(
        PermissionModule.MODERATION.value, "Бан и разбан («👤 Пользователи»)"
    ),
    PermissionModule.ACTIVITIES.value: Module(
        PermissionModule.ACTIVITIES.value, "Мероприятия и голосования"
    ),
}


def personal_modules(user: User) -> set[str]:
    if not user.custom_permissions:
        return set()
    return {m for m in user.custom_permissions.get("modules", []) if m in MODULES}


async def effective_modules(session: AsyncSession, user: User) -> set[str]:
    """Итоговые модули человека: полный админ — все; иначе группа + личные."""
    if user.current_role in FULL_ADMIN_ROLES:
        return set(MODULES)
    modules = personal_modules(user)
    if user.permission_group_id is not None:
        group = await permission_repo.get(session, user.permission_group_id)
        if group is not None:
            modules |= {m for m in (group.modules or []) if m in MODULES}
    return modules


async def has_permission(
    session: AsyncSession, user: User | None, module: PermissionModule
) -> bool:
    if user is None or user.current_role == UserRole.BANNED:
        return False
    if user.current_role in FULL_ADMIN_ROLES:
        return True
    return module.value in await effective_modules(session, user)


async def toggle_group_module(
    session: AsyncSession, admin: User, group: PermissionGroup, module_key: str
) -> bool:
    """Включает/выключает модуль у группы. Возвращает новое состояние (включён?)."""
    modules = set(group.modules or [])
    enabled = module_key not in modules
    if enabled:
        modules.add(module_key)
    else:
        modules.discard(module_key)
    group.modules = sorted(modules)
    await audit_repo.add(
        session,
        AuditAction.PERM_GROUP_UPDATED,
        actor_tg_id=admin.tg_id,
        target_entity_type="permission_group",
        target_entity_id=str(group.group_id),
        meta={"module": module_key, "enabled": enabled, "modules": group.modules},
    )
    await session.commit()
    return enabled


async def toggle_user_module(
    session: AsyncSession, admin: User, target: User, module_key: str
) -> bool:
    """Включает/выключает личный модуль у человека. Возвращает новое состояние."""
    modules = personal_modules(target)
    enabled = module_key not in modules
    if enabled:
        modules.add(module_key)
    else:
        modules.discard(module_key)
    target.custom_permissions = {**(target.custom_permissions or {}), "modules": sorted(modules)}
    await audit_repo.add(
        session,
        AuditAction.USER_PERMISSIONS_CHANGED,
        actor_tg_id=admin.tg_id,
        target_tg_id=target.tg_id,
        meta={"module": module_key, "enabled": enabled, "personal_modules": sorted(modules)},
    )
    await session.commit()
    return enabled


async def set_user_group(
    session: AsyncSession, admin: User, target: User, group: PermissionGroup | None
) -> None:
    target.permission_group_id = group.group_id if group else None
    await audit_repo.add(
        session,
        AuditAction.USER_PERMISSIONS_CHANGED,
        actor_tg_id=admin.tg_id,
        target_tg_id=target.tg_id,
        meta={"group_id": group.group_id if group else None,
              "group_name": group.name if group else None},
    )
    await session.commit()


async def create_group(session: AsyncSession, admin: User, name: str) -> PermissionGroup:
    group = await permission_repo.create(session, name)
    await audit_repo.add(
        session,
        AuditAction.PERM_GROUP_CREATED,
        actor_tg_id=admin.tg_id,
        target_entity_type="permission_group",
        target_entity_id=str(group.group_id),
        meta={"name": name},
    )
    await session.commit()
    return group


async def delete_group(session: AsyncSession, admin: User, group: PermissionGroup) -> None:
    group_id, name = group.group_id, group.name
    await session.delete(group)
    await audit_repo.add(
        session,
        AuditAction.PERM_GROUP_DELETED,
        actor_tg_id=admin.tg_id,
        target_entity_type="permission_group",
        target_entity_id=str(group_id),
        meta={"name": name},
    )
    await session.commit()
