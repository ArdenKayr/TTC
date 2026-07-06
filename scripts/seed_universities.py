"""Load universities from a CSV file (skips names that already exist).

CSV format (delimiter ';'), header required:
    name;city;aliases
    Национальный исследовательский университет «Высшая школа экономики»;Москва;ВШЭ|Вышка

Usage:
    docker compose run --rm bot python -m scripts.seed_universities data/universities.csv
"""
import asyncio
import csv
import sys

from sqlalchemy import select

from bot.db.base import async_session_factory
from bot.db.models import University, UniversityAlias
from bot.db.repositories import university_repo


async def run(path: str) -> None:
    created = 0
    aliases_created = 0
    async with async_session_factory() as session:
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                name = (row.get("name") or "").strip()
                if not name:
                    continue
                university = await university_repo.find_by_exact_name(session, name)
                if university is None:
                    university = University(
                        canonical_name=name, city=(row.get("city") or "").strip() or None
                    )
                    session.add(university)
                    await session.flush()
                    created += 1
                aliases = [a.strip() for a in (row.get("aliases") or "").split("|") if a.strip()]
                if not aliases:
                    continue
                result = await session.execute(
                    select(UniversityAlias.alias_text).where(
                        UniversityAlias.university_id == university.university_id
                    )
                )
                existing = {a.lower() for a in result.scalars()}
                for alias in aliases:
                    if alias.lower() not in existing:
                        session.add(
                            UniversityAlias(
                                university_id=university.university_id, alias_text=alias
                            )
                        )
                        aliases_created += 1
        await session.commit()
    print(f"OK: universities created: {created}, aliases created: {aliases_created}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.seed_universities <path/to/file.csv>")
        sys.exit(1)
    asyncio.run(run(sys.argv[1]))
