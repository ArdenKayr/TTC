import re

from sqlalchemy import desc, func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import University, UniversityAlias

_PUNCT_RE = re.compile(r"[^\w\s]+", re.UNICODE)
_SPACES_RE = re.compile(r"\s+")


def normalize_query(query: str) -> str:
    """Убирает знаки препинания и спецсимволы, схлопывает пробелы.

    Регистр не трогаем: триграммный поиск Postgres (pg_trgm) сам не различает
    регистр и пунктуацию, а нормализация нужна для подстрочного поиска (ilike).
    """
    return _SPACES_RE.sub(" ", _PUNCT_RE.sub(" ", query)).strip()


async def get(session: AsyncSession, university_id: int) -> University | None:
    return await session.get(University, university_id)


async def search(session: AsyncSession, query: str, limit: int = 5) -> list[University]:
    """Поиск вуза по названию и вариантам, лояльный к опечаткам и сокращениям.

    Сходство считается и по полному названию, и по каждому варианту поиска.
    similarity — общее сходство строк (ловит опечатки),
    word_similarity — сходство запроса с куском строки (ловит короткие
    запросы вида «политех» против длинного официального названия).
    """
    query = normalize_query(query)
    if not query:
        return []
    name_sim = func.similarity(University.canonical_name, query)
    name_wsim = func.word_similarity(query, University.canonical_name)
    alias_sim = func.similarity(UniversityAlias.alias_text, query)
    alias_wsim = func.word_similarity(query, UniversityAlias.alias_text)
    score = func.max(
        func.greatest(
            name_sim, name_wsim, func.coalesce(alias_sim, 0), func.coalesce(alias_wsim, 0)
        )
    ).label("score")
    stmt = (
        select(University, score)
        .outerjoin(UniversityAlias, UniversityAlias.university_id == University.university_id)
        .where(
            or_(
                name_sim > 0.2,
                name_wsim > 0.45,
                University.canonical_name.ilike(f"%{query}%"),
                alias_sim > 0.3,
                alias_wsim > 0.5,
                UniversityAlias.alias_text.ilike(f"%{query}%"),
            )
        )
        .group_by(University.university_id)
        .order_by(desc(literal_column("score")))
        .limit(limit)
    )
    result = await session.execute(stmt)
    return [row[0] for row in result.all()]


async def list_all(session: AsyncSession, limit: int = 50, offset: int = 0) -> list[University]:
    """Все вузы по алфавиту, страницами — для живого inline-списка."""
    result = await session.execute(
        select(University).order_by(University.canonical_name).limit(limit).offset(offset)
    )
    return list(result.scalars().all())


async def find_by_exact_name(session: AsyncSession, name: str) -> University | None:
    result = await session.execute(
        select(University).where(func.lower(University.canonical_name) == name.lower())
    )
    return result.scalar_one_or_none()


async def create_verified(session: AsyncSession, name: str) -> University:
    university = University(canonical_name=name, is_verified=True)
    session.add(university)
    await session.flush()
    return university


async def alias_exists(session: AsyncSession, university_id: int, alias_text: str) -> bool:
    result = await session.execute(
        select(UniversityAlias.alias_id)
        .where(
            UniversityAlias.university_id == university_id,
            func.lower(UniversityAlias.alias_text) == alias_text.lower(),
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def add_alias(session: AsyncSession, university_id: int, alias_text: str) -> None:
    session.add(UniversityAlias(university_id=university_id, alias_text=alias_text))
    await session.flush()
