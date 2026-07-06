from sqlalchemy import desc, func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import University, UniversityAlias


async def get(session: AsyncSession, university_id: int) -> University | None:
    return await session.get(University, university_id)


async def search(session: AsyncSession, query: str, limit: int = 5) -> list[University]:
    name_sim = func.similarity(University.canonical_name, query)
    alias_sim = func.similarity(UniversityAlias.alias_text, query)
    stmt = (
        select(
            University,
            func.max(func.greatest(name_sim, func.coalesce(alias_sim, 0))).label("score"),
        )
        .outerjoin(UniversityAlias, UniversityAlias.university_id == University.university_id)
        .where(
            or_(
                name_sim > 0.2,
                University.canonical_name.ilike(f"%{query}%"),
                alias_sim > 0.3,
                UniversityAlias.alias_text.ilike(f"%{query}%"),
            )
        )
        .group_by(University.university_id)
        .order_by(desc(literal_column("score")))
        .limit(limit)
    )
    result = await session.execute(stmt)
    return [row[0] for row in result.all()]


async def find_by_exact_name(session: AsyncSession, name: str) -> University | None:
    result = await session.execute(
        select(University).where(func.lower(University.canonical_name) == name.lower())
    )
    return result.scalar_one_or_none()


async def create_unverified(session: AsyncSession, name: str) -> University:
    university = University(canonical_name=name, is_verified=False)
    session.add(university)
    await session.flush()
    return university
