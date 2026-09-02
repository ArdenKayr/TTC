from html import escape

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import Message

from bot import texts
from bot.config import settings
from bot.db.models import User
from bot.enums import FULL_ADMIN_ROLES
from bot.keyboards.common_kb import admin_call_kb
from bot.routers.group.admin_chat import SERVICE_MESSAGE
from bot.services import notification_service

router = Router(name="topic_guards")


def _message_link(message: Message) -> str:
    internal_id = str(message.chat.id).removeprefix("-100")
    return f"https://t.me/c/{internal_id}/{message.message_id}"


def _is_main_group(message: Message) -> bool:
    return settings.group_chat_id is not None and message.chat.id == settings.group_chat_id


def _speaks_as_the_group(message: Message) -> bool:
    """Сообщение отправлено от лица самой группы — то есть анонимным админом.

    Telegram прячет такого отправителя: вместо человека в сообщении стоит
    служебный аккаунт, а настоящее авторство видно только по `sender_chat`.
    Искать его в базе бесполезно — он там не появится никогда, и охрана тем
    принимала админа, пишущего «от группы», за постороннего и стирала его
    объявления.

    Писать от лица группы может только её администратор — это правило самого
    Telegram, поэтому проверять больше нечего. Чужой канал сюда не подходит:
    сверяем, что говорят от лица именно этой группы, а не от имени чьего-то
    постороннего канала.
    """
    return message.sender_chat is not None and message.sender_chat.id == message.chat.id


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


@router.message(Command("id"), F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def cmd_chat_id(message: Message, db_user: User | None) -> None:
    """Называет номер чата и темы — их вписывают в настройки бота.

    Закрытую группу нельзя найти по имени: имени у неё нет. Раньше номер брался
    из публичного имени сам, теперь взять его больше неоткуда — кроме как
    спросить у самого бота.

    Отвечает в любой группе, в том числе ещё не прописанной в настройках: иначе
    команда молчала бы именно в тот момент, ради которого она и сделана.
    """
    if db_user is None or db_user.current_role not in FULL_ADMIN_ROLES:
        return
    answer = texts.CHAT_ID_REPORT.format(chat_id=message.chat.id)
    if message.message_thread_id is not None:
        answer += texts.CHAT_ID_TOPIC.format(thread_id=message.message_thread_id)
    await message.reply(answer)


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}), SERVICE_MESSAGE)
async def delete_group_service_message(message: Message) -> None:
    """Служебный мусор в общей группе («X присоединился» и т.п.) — удаляем.

    Такие сообщения Telegram публикует в теме General. Нужно право
    «Удаление сообщений» в группе — без него молча оставляем.
    """
    if not _is_main_group(message):
        return
    try:
        await message.delete()
    except TelegramAPIError:
        pass


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def group_message(message: Message, db_user: User | None) -> None:
    if not _is_main_group(message):
        return

    read_only_topics = {settings.topic_announcements_id, settings.topic_afisha_id} - {None}
    is_admin = _speaks_as_the_group(message) or (
        db_user is not None and db_user.current_role in FULL_ADMIN_ROLES
    )
    if message.message_thread_id in read_only_topics and not is_admin:
        try:
            await message.delete()
        except TelegramAPIError:
            pass
        return

    text_lower = message.text.lower() if message.text else ""
    if "@admin" in text_lower or "@админ" in text_lower:
        await _notify_admin_call(message)
