from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User
from bot.enums import UserRole


async def get_by_tg_id(session: AsyncSession, tg_id: int) -> User | None:
    return await session.get(User, tg_id)


async def list_by_permission_group(session: AsyncSession, group_id: int) -> list[User]:
    result = await session.execute(
        select(User).where(User.permission_group_id == group_id).order_by(User.display_name)
    )
    return list(result.scalars().all())


async def get_by_username(session: AsyncSession, username: str) -> User | None:
    result = await session.execute(
        select(User).where(User.username.ilike(username.lstrip("@")))
    )
    return result.scalar_one_or_none()


async def label_map(session: AsyncSession, tg_ids: set[int]) -> dict[int, str]:
    """{tg_id: "Имя (@ник)"} для тех из tg_ids, кто есть в users.

    Для логов и карточек ошибок — чтобы вместо голого номера аккаунта
    показывалось, кто это. Тех, кого в users нет (не зарегистрирован
    или аккаунт удалён), в словаре не будет — вызывающий код сам решает,
    как показать номер без имени.
    """
    if not tg_ids:
        return {}
    result = await session.execute(
        select(User.tg_id, User.display_name, User.username).where(User.tg_id.in_(tg_ids))
    )
    labels: dict[int, str] = {}
    for tg_id, display_name, username in result.all():
        handle = f"@{username}" if username else f"id {tg_id}"
        labels[tg_id] = f"{display_name} ({handle})"
    return labels


async def upsert_from_registration(
    session: AsyncSession,
    *,
    tg_id: int,
    username: str | None,
    display_name: str,
    university_id: int | None,
    university_group: str | None,
    birth_date,
    about_text: str | None = None,
) -> User:
    stmt = (
        insert(User)
        .values(
            tg_id=tg_id,
            username=username,
            display_name=display_name,
            university_id=university_id,
            university_group=university_group,
            birth_date=birth_date,
            about_text=about_text,
            current_role=UserRole.USER,
        )
        .on_conflict_do_update(
            index_elements=[User.tg_id],
            set_={
                "username": username,
                "display_name": display_name,
                "university_id": university_id,
                "university_group": university_group,
                "birth_date": birth_date,
                "about_text": about_text,
                "current_role": UserRole.USER,
            },
        )
    )
    await session.execute(stmt)
    return await session.get(User, tg_id)
