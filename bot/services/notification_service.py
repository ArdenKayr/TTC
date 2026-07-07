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


async def send_admin_report(bot: Bot, text: str) -> None:
    await bot.send_message(
        settings.admin_chat_id,
        text,
        message_thread_id=settings.admin_topic_reports_id,
    )


async def dm_user(bot: Bot, tg_id: int, text: str) -> bool:
    try:
        await bot.send_message(tg_id, text)
        return True
    except TelegramAPIError as e:
        logger.warning("Failed to DM user %s: %s", tg_id, e)
        return False
