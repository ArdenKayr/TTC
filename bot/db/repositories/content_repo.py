from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import ContentBlock


async def get(session: AsyncSession, slot: str) -> ContentBlock | None:
    return await session.get(ContentBlock, slot)


async def get_or_create(session: AsyncSession, slot: str) -> ContentBlock:
    block = await session.get(ContentBlock, slot)
    if block is None:
        block = ContentBlock(slot=slot)
        session.add(block)
        await session.flush()
    return block
