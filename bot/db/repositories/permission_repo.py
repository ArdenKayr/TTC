from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import PermissionGroup


async def get(session: AsyncSession, group_id: int) -> PermissionGroup | None:
    return await session.get(PermissionGroup, group_id)


async def list_all(session: AsyncSession) -> list[PermissionGroup]:
    result = await session.execute(select(PermissionGroup).order_by(PermissionGroup.name))
    return list(result.scalars().all())


async def find_by_name(session: AsyncSession, name: str) -> PermissionGroup | None:
    result = await session.execute(
        select(PermissionGroup).where(PermissionGroup.name.ilike(name))
    )
    return result.scalar_one_or_none()


async def create(session: AsyncSession, name: str) -> PermissionGroup:
    group = PermissionGroup(name=name, modules=[])
    session.add(group)
    await session.flush()
    return group
