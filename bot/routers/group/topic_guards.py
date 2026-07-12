from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message

from bot import texts
from bot.config import settings
from bot.db.models import User
from bot.enums import UserRole
from bot.services import notification_service

router = Router(name="topic_guards")


def _message_link(message: Message) -> str:
    internal_id = str(message.chat.id).removeprefix("-100")
    return f"https://t.me/c/{internal_id}/{message.message_id}"


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def group_message(message: Message, db_user: User | None) -> None:
    if settings.group_chat_id is None or message.chat.id != settings.group_chat_id:
        return

    read_only_topics = {settings.topic_announcements_id, settings.topic_afisha_id} - {None}
    is_admin = db_user is not None and db_user.current_role == UserRole.ADMIN
    if message.message_thread_id in read_only_topics and not is_admin:
        try:
            await message.delete()
        except TelegramAPIError:
            pass
        return

    if message.text and "@admin" in message.text.lower():
        sender = message.from_user
        who = f"@{sender.username}" if sender.username else sender.full_name
        await notification_service.send_admin_report(
            message.bot,
            texts.ADMIN_CALL_REPORT.format(who=who, link=_message_link(message)),
        )
