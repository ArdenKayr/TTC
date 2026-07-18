"""Assign the very first admin/superadmin/owner from the server console.

The owner role can ONLY be granted here — never via the bot.

Usage:
    docker compose run --rm bot python -m scripts.bootstrap_admin --tg-id 123456789 --name "Имя" [--role owner]
"""
import argparse
import asyncio

from sqlalchemy.dialects.postgresql import insert

from bot.db.base import async_session_factory
from bot.db.models import User
from bot.enums import UserRole

_ALLOWED = {UserRole.ADMIN, UserRole.SUPERADMIN, UserRole.OWNER}


async def run(tg_id: int, name: str, username: str | None, role: UserRole) -> None:
    async with async_session_factory() as session:
        stmt = (
            insert(User)
            .values(
                tg_id=tg_id,
                display_name=name,
                username=username,
                current_role=role,
            )
            .on_conflict_do_update(
                index_elements=[User.tg_id],
                set_={"current_role": role, "display_name": name},
            )
        )
        await session.execute(stmt)
        await session.commit()
    print(f"OK: {name} (tg_id={tg_id}) is now {role.value}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tg-id", type=int, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--username", default=None)
    parser.add_argument(
        "--role", default="admin", choices=sorted(r.value for r in _ALLOWED)
    )
    args = parser.parse_args()
    asyncio.run(run(args.tg_id, args.name, args.username, UserRole(args.role)))
