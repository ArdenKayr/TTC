from html import escape

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import Message

from bot import texts
from bot.config import settings
from bot.db.models import User
from bot.enums import UserRole
from bot.keyboards.common_kb import admin_call_kb
from bot.services import notification_service

router = Router(name="topic_guards")


def _message_link(message: Message) -> str:
    internal_id = str(message.chat.id).removeprefix("-100")
    return f"https://t.me/c/{internal_id}/{message.message_id}"


def _is_main_group(message: Message) -> bool:
    return settings.group_chat_id is not None and message.chat.id == settings.group_chat_id


async def _notify_admin_call(message: Message) -> None:
    sender = message.from_user
    who = f"@{sender.username}" if sender.username else sender.full_name
    await notification_service.send_admin_report(
        message.bot,
        texts.ADMIN_CALL_REPORT.format(who=escape(who), link=_message_link(message)),
        keyboard=admin_call_kb(),
    )


@router.message(Command("admin"), F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def cmd_admin_call(message: Message) -> None:
    if _is_main_group(message):
        await _notify_admin_call(message)


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def group_message(message: Message, db_user: User | None) -> None:
    if not _is_main_group(message):
        return

    read_only_topics = {settings.topic_announcements_id, settings.topic_afisha_id} - {None}
    is_admin = db_user is not None and db_user.current_role == UserRole.ADMIN
    if message.message_thread_id in read_only_topics and not is_admin:
        try:
            await message.delete()
        except TelegramAPIError:
            pass
        return

    text_lower = message.text.lower() if message.text else ""
    if "@admin" in text_lower or "@админ" in text_lower:
        await _notify_admin_call(message)
