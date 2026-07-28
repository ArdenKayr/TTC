import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup

from bot.config import settings

logger = logging.getLogger(__name__)


async def send_admin_card(
    bot: Bot, text: str, keyboard: InlineKeyboardMarkup | None = None
) -> None:
    await bot.send_message(
        settings.admin_chat_id,
        text,
        reply_markup=keyboard,
        message_thread_id=settings.admin_topic_applications_id,
    )


async def send_admin_report(
    bot: Bot, text: str, keyboard: InlineKeyboardMarkup | None = None
) -> None:
    await bot.send_message(
        settings.admin_chat_id,
        text,
        reply_markup=keyboard,
        message_thread_id=settings.admin_topic_reports_id,
    )


async def dm_user(bot: Bot, tg_id: int, text: str) -> bool:
    try:
        await bot.send_message(tg_id, text)
        return True
    except TelegramAPIError as e:
        logger.warning("Failed to DM user %s: %s", tg_id, e)
        return False


async def send_afisha_card(bot: Bot, text: str) -> int | None:
    """Карточка мероприятия в топик «Афиша». Возвращает message_id или None."""
    if settings.group_chat_id is None:
        return None
    try:
        message = await bot.send_message(
            settings.group_chat_id, text, message_thread_id=settings.topic_afisha_id
        )
        return message.message_id
    except TelegramAPIError as e:
        logger.warning("Failed to post afisha card: %s", e)
        return None


async def edit_afisha_card(bot: Bot, message_id: int, text: str) -> bool:
    """Правка карточки в Афише (пометка «Прошло»/«Отменено»)."""
    if settings.group_chat_id is None:
        return False
    try:
        await bot.edit_message_text(text, chat_id=settings.group_chat_id, message_id=message_id)
        return True
    except TelegramAPIError as e:
        logger.warning("Failed to edit afisha card %s: %s", message_id, e)
        return False


async def send_vote_poll(
    bot: Bot, question: str, options: list[str], is_anonymous: bool = True
) -> int | None:
    """Опрос в топик «Голосования». Возвращает message_id или None."""
    if settings.group_chat_id is None:
        return None
    try:
        message = await bot.send_poll(
            settings.group_chat_id,
            question,
            options,
            is_anonymous=is_anonymous,
            message_thread_id=settings.topic_voting_id,
        )
        return message.message_id
    except TelegramAPIError as e:
        logger.warning("Failed to post vote poll: %s", e)
        return None
