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
from bot.routers.activities import router as activities_router
from bot.routers.admin.activity_review import router as activity_review_router
from bot.routers.admin.content_admin import router as content_admin_router
from bot.routers.admin.crud_admin import router as crud_admin_router
from bot.routers.admin.owner_panel import router as owner_panel_router
from bot.routers.admin.scenario_admin import router as scenario_admin_router
from bot.routers.admin.permissions_admin import router as permissions_admin_router
from bot.routers.admin.registration_review import router as registration_review_router
from bot.routers.admin.university_review import router as university_review_router
from bot.routers.common import router as common_router
from bot.routers.group.admin_chat import router as admin_chat_router
from bot.routers.group.topic_guards import router as topic_guards_router
from bot.routers.profile import router as profile_router
from bot.routers.registration import router as registration_router
from bot.routers.superadmin import router as superadmin_router
from bot.routers.user_menu import router as user_menu_router
from bot.services.error_service import on_error

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
    # Контуров два — боевой и тестовый (docs/TEST_ENV.md). В логах они выглядят
    # одинаково, поэтому контур называется первой же строкой.
    if settings.is_test:
        logging.warning("ТЕСТОВЫЙ КОНТУР: отдельный бот, своя база, тестовые чаты")
    else:
        logging.info("Боевой контур")

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
        activity_review_router,
        permissions_admin_router,
        content_admin_router,
        registration_router,
        activities_router,
        superadmin_router,
        crud_admin_router,
        scenario_admin_router,
        owner_panel_router,
        user_menu_router,
        profile_router,
        admin_chat_router,
        topic_guards_router,
        common_router,
    )
    # Любая необработанная ошибка хендлера: в error_log + карточка владельцу в ЛС.
    dp.errors.register(on_error)

    # drop_pending_updates=False: апдейты, накопившиеся за время простоя (перезапуск,
    # деплой), при старте ДОРАБАТЫВАЮТСЯ, а не выбрасываются молча. С True человек мог
    # нажать «Отправить» анкету ровно в момент рестарта — заявка терялась без следа
    # и без единой записи в логах (апдейт просто не долетал до кода бота вообще).
    await bot.delete_webhook(drop_pending_updates=False)
    await resolve_group_chat_id(bot)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
