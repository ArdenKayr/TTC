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
from bot.routers.admin.permissions_admin import router as permissions_admin_router
from bot.routers.admin.registration_review import router as registration_review_router
from bot.routers.admin.report_review import router as report_review_router
from bot.routers.admin.scenario_admin import router as scenario_admin_router
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
logger = logging.getLogger(__name__)


async def check_invite_rights(bot: Bot, chat_id: int) -> None:
    """Может ли бот выдавать ссылки в группу. Только предупреждение в журнал.

    Группа закрытая: попасть в неё можно единственным способом — по ссылке,
    которую создаёт бот. Без права «Приглашать пользователей по ссылке» он
    молча перестанет пускать людей, и это выяснится не из журнала, а из жалоб
    тех, кто остался за дверью. Поэтому спрашиваем сразу при запуске.
    """
    try:
        me = await bot.get_chat_member(chat_id, (await bot.me()).id)
    except TelegramAPIError as e:
        logger.warning("Не удалось проверить права бота в группе %s: %s", chat_id, e)
        return
    if getattr(me, "can_invite_users", False):
        return
    logger.warning(
        "Бот в группе %s имеет статус %r и не может приглашать по ссылке: "
        "люди не смогут вступить. Нужны права администратора, среди них "
        "«Приглашать пользователей по ссылке».",
        chat_id,
        me.status,
    )


async def resolve_group_chat_id(bot: Bot) -> None:
    """Приводит GROUP_CHAT_ID к числу и проверяет, что группа боту доступна.

    В настройке допустимо и публичное имя, но у закрытой группы его нет —
    только число. Число раньше принималось на веру: ошибка в нём выглядела для
    людей ровно как поломка ссылок и Афиши, а в журнале не оставляла ни строки.
    Теперь спрашиваем Telegram в обоих случаях.
    """
    configured = settings.group_chat_id
    if configured is None:
        logger.warning("GROUP_CHAT_ID не задан: групповая часть бота выключена.")
        return
    try:
        chat = await bot.get_chat(configured)
    except TelegramAPIError as e:
        logger.warning("Не удалось открыть группу %r: %s", configured, e)
        if isinstance(configured, str):
            # Имя, которое не открылось, слать некуда: обработчики сравнивают
            # числовые id, а send_message по такому имени всё равно упадёт.
            settings.group_chat_id = None
        # Числу верим дальше: оно задано человеком явно, и разовый сбой связи
        # не повод выключать группу до следующего перезапуска.
        return
    settings.group_chat_id = chat.id
    logger.info("Группа найдена: %r -> %s", configured, chat.id)
    await check_invite_rights(bot, chat.id)


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
        activity_review_router,
        report_review_router,
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
