from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import ReferralLink, ReferralVisit


async def get_link(session: AsyncSession, code: str) -> ReferralLink | None:
    return await session.get(ReferralLink, code)


async def create_link(
    session: AsyncSession, *, code: str, owner_tg_id: int, title: str, created_by: int
) -> ReferralLink:
    link = ReferralLink(
        code=code, owner_tg_id=owner_tg_id, title=title, created_by=created_by
    )
    session.add(link)
    await session.flush()
    return link


async def delete_link(session: AsyncSession, link: ReferralLink) -> None:
    """Удаляет ссылку вместе с её переходами (в базе стоит каскад)."""
    await session.delete(link)
    await session.flush()


async def list_links(
    session: AsyncSession, owner_tg_id: int | None = None
) -> list[ReferralLink]:
    """Ссылки одного человека или все сразу — самые новые сверху."""
    query = select(ReferralLink).order_by(ReferralLink.created_at.desc())
    if owner_tg_id is not None:
        query = query.where(ReferralLink.owner_tg_id == owner_tg_id)
    result = await session.execute(query)
    return list(result.scalars())


async def count_links(session: AsyncSession, owner_tg_id: int) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(ReferralLink)
        .where(ReferralLink.owner_tg_id == owner_tg_id)
    )
    return int(result.scalar_one())


async def stats(session: AsyncSession, codes: list[str]) -> dict[str, tuple[int, int, int]]:
    """Три числа на каждую ссылку: открыли бота, подали анкету, приняты.

    Одним запросом на весь список: ссылок у владельца бывает десяток, и по
    запросу на каждую панель открывалась бы заметно дольше.
    """
    if not codes:
        return {}
    result = await session.execute(
        select(
            ReferralVisit.code,
            func.count(),
            func.count(ReferralVisit.applied_at),
            func.count(ReferralVisit.approved_at),
        )
        .where(ReferralVisit.code.in_(codes))
        .group_by(ReferralVisit.code)
    )
    counted = {code: (visits, applied, approved) for code, visits, applied, approved in result}
    return {code: counted.get(code, (0, 0, 0)) for code in codes}


async def get_visit(session: AsyncSession, tg_id: int) -> ReferralVisit | None:
    return await session.get(ReferralVisit, tg_id)


async def add_visit(session: AsyncSession, *, code: str, tg_id: int) -> ReferralVisit | None:
    """Записывает переход. None — человек уже числится за какой-то ссылкой.

    Первая ссылка человека не перебивается второй: см. «первое касание» в
    описании модели `ReferralVisit`.
    """
    if await get_visit(session, tg_id) is not None:
        return None
    visit = ReferralVisit(tg_id=tg_id, code=code)
    session.add(visit)
    await session.flush()
    return visit


async def mark_applied(session: AsyncSession, tg_id: int, when: datetime) -> None:
    """Отмечает, что пришедший по ссылке дошёл до отправки анкеты.

    Проставляется только первый раз: человек после отказа подаёт анкету
    заново, и «дошёл до анкеты» от этого не удваивается.
    """
    await session.execute(
        update(ReferralVisit)
        .where(ReferralVisit.tg_id == tg_id, ReferralVisit.applied_at.is_(None))
        .values(applied_at=when)
    )


async def mark_approved(session: AsyncSession, tg_id: int, when: datetime) -> None:
    await session.execute(
        update(ReferralVisit)
        .where(ReferralVisit.tg_id == tg_id, ReferralVisit.approved_at.is_(None))
        .values(approved_at=when)
    )
