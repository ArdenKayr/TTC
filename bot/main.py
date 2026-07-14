import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.storage.redis import RedisStorage

from bot.config import settings
from bot.middlewares.ban_guard import BanGuardMiddleware
from bot.middlewares.db_session import DbSessionMiddleware
from bot.middlewares.role_guard import UserLoaderMiddleware
from bot.routers.admin.content_admin import router as content_admin_router
from bot.routers.admin.moderation import router as moderation_router
from bot.routers.admin.permissions_admin import router as permissions_admin_router
from bot.routers.admin.registration_review import router as registration_review_router
from bot.routers.admin.university_review import router as university_review_router
from bot.routers.common import router as common_router
from bot.routers.group.topic_guards import router as topic_guards_router
from bot.routers.registration import router as registration_router

logging.basicConfig(level=logging.INFO)


async def resolve_group_chat_id(bot: Bot) -> None:
    """GROUP_CHAT_ID may be a public @username; handlers compare numeric chat ids."""
    if not isinstance(settings.group_chat_id, str):
        return
    try:
        chat = await bot.get_chat(settings.group_chat_id)
        settings.group_chat_id = chat.id
        logging.info("Resolved group %s -> %s", chat.username, chat.id)
    except TelegramAPIError as e:
        logging.warning("Failed to resolve GROUP_CHAT_ID %r: %s", settings.group_chat_id, e)
        settings.group_chat_id = None


async def main() -> None:
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    storage = RedisStorage.from_url(settings.redis_url)
    dp = Dispatcher(storage=storage)

    dp.update.outer_middleware(DbSessionMiddleware())
    # Outer (pre-filter) so that db_user is available inside filters like IsAdmin.
    for observer in (dp.message, dp.callback_query):
        observer.outer_middleware(UserLoaderMiddleware())
        observer.outer_middleware(BanGuardMiddleware())

    dp.include_routers(
        registration_review_router,
        university_review_router,
        permissions_admin_router,
        moderation_router,
        content_admin_router,
        registration_router,
        topic_guards_router,
        common_router,
    )

    await bot.delete_webhook(drop_pending_updates=True)
    await resolve_group_chat_id(bot)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
