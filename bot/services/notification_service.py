import logging
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup

from bot import texts
from bot.config import settings
from bot.services.content_service import CAPTION_LIMIT

logger = logging.getLogger(__name__)


async def deliver_card(
    bot: Bot,
    chat_id: int | str,
    text: str,
    keyboard: InlineKeyboardMarkup | None = None,
    photo_file_id: str | None = None,
    thread: int | None = None,
) -> None:
    """Одна карточка в любой чат: с обложкой или без.

    Кнопки решения всегда на том сообщении, где лежит текст: админ читает и
    нажимает в одном месте. Обложка идёт подписью, если текст в неё влезает,
    и отдельной картинкой сверху, если нет — Telegram в подпись пускает
    только 1024 символа и молча обрезал бы остальное.

    Ошибки не ловит: что делать с недоставленной карточкой, решает тот, кто
    её отправляет, — в админ-чате и в личке админа это разные решения.
    """
    if photo_file_id is None:
        await bot.send_message(chat_id, text, reply_markup=keyboard, message_thread_id=thread)
        return
    if len(text) <= CAPTION_LIMIT:
        await bot.send_photo(
            chat_id,
            photo_file_id,
            caption=text,
            reply_markup=keyboard,
            message_thread_id=thread,
        )
        return
    await bot.send_photo(chat_id, photo_file_id, message_thread_id=thread)
    await bot.send_message(chat_id, text, reply_markup=keyboard, message_thread_id=thread)


async def send_admin_card(
    bot: Bot,
    text: str,
    keyboard: InlineKeyboardMarkup | None = None,
    photo_file_id: str | None = None,
    *,
    source: str = "Карточка заявки",
    tg_id: int | None = None,
) -> bool:
    """Карточка заявки в админ-чат. С картинкой — если заявка её принесла.

    Кнопки решения всегда на том сообщении, где лежит текст карточки: админ
    читает и нажимает в одном месте, а не ищет кнопки под соседней картинкой.

    **Отправка не имеет права уронить подачу заявки.** Заявка к этому моменту
    уже лежит в базе, и Telegram, отказавший в доставке карточки, ничего в
    этом не меняет: отказать он может по причинам, к заявке отношения не
    имеющим — упёрлись в лимит сообщений в группу (20 в минуту, а на наплыве
    заявок это первое, во что бот упирается), чат недоступен, права отобраны.
    Поэтому неудача записывается в журнал владельцу, а заявка остаётся
    ждать в очереди «🛠 Админство» → «📥 Заявки», откуда её достанут руками.

    Возвращает, дошла ли карточка.
    """
    # Локальный импорт: error_service тянет за собой пол-базы, а нужен он тут
    # только в редкой ветке отказа.
    from bot.services import error_service

    try:
        await deliver_card(
            bot,
            settings.admin_chat_id,
            text,
            keyboard,
            photo_file_id,
            thread=settings.admin_topic_applications_id,
        )
    except TelegramAPIError as e:
        logger.warning("Failed to send admin card (%s): %s", source, e)
        await error_service.report_issue(
            bot,
            source=source,
            tg_id=tg_id,
            note=f"Заявка сохранена, но карточка не ушла в админ-чат: {e}. "
            f"Разобрать её можно в «{texts.BTN.ADMIN_MODE}» → «{texts.BTN.ADMIN_PANEL_QUEUE}».",
        )
        return False
    return True


async def send_admin_report(
    bot: Bot, text: str, keyboard: InlineKeyboardMarkup | None = None
) -> int:
    """Сообщение в тему репортов. Возвращает message_id — по нему правится карточка.

    Карточку репорта приходится править при каждой смене статуса: иначе в чате
    копятся карточки с устаревшим статусом и живыми кнопками, и следующий админ
    жмёт «В работе» по уже закрытому.
    """
    message = await bot.send_message(
        settings.admin_chat_id,
        text,
        reply_markup=keyboard,
        message_thread_id=settings.admin_topic_reports_id,
    )
    return message.message_id


async def edit_admin_card(
    bot: Bot, message_id: int, text: str, keyboard: InlineKeyboardMarkup | None = None
) -> bool:
    """Правка карточки в админ-чате. Неудача не должна ронять действие админа.

    Карточку могли удалить из чата, а Telegram отказывает и тогда, когда текст
    не изменился. Ни то, ни другое не повод отменять уже принятое решение —
    поэтому здесь только запись в журнал.
    """
    try:
        await bot.edit_message_text(
            text, chat_id=settings.admin_chat_id, message_id=message_id, reply_markup=keyboard
        )
        return True
    except TelegramAPIError as e:
        logger.warning("Failed to edit admin card %s: %s", message_id, e)
        return False


async def dm_user(bot: Bot, tg_id: int, text: str) -> bool:
    try:
        await bot.send_message(tg_id, text)
        return True
    except TelegramAPIError as e:
        logger.warning("Failed to DM user %s: %s", tg_id, e)
        return False


@dataclass(frozen=True)
class AfishaPost:
    """Куда потом ставить пометку «Прошло»/«Отменено».

    Пост в Афише бывает двух видов, и правятся они разными способами. Если
    карточка влезла в подпись под картинкой — это одно сообщение, и меняется
    подпись. Если описание длиннее 1024 символов, Telegram подпись не примет:
    тогда картинка уходит отдельно, а карточка — обычным текстом под ней.
    """

    message_id: int
    is_caption: bool


async def send_afisha_card(
    bot: Bot, text: str, photo_file_id: str | None = None
) -> AfishaPost | None:
    """Карточка мероприятия в топик «Афиша». None — если отправить не вышло."""
    if settings.group_chat_id is None:
        return None
    thread = settings.topic_afisha_id
    try:
        if photo_file_id is not None and len(text) <= CAPTION_LIMIT:
            message = await bot.send_photo(
                settings.group_chat_id, photo_file_id, caption=text, message_thread_id=thread
            )
            return AfishaPost(message.message_id, is_caption=True)
        if photo_file_id is not None:
            await bot.send_photo(settings.group_chat_id, photo_file_id, message_thread_id=thread)
        message = await bot.send_message(settings.group_chat_id, text, message_thread_id=thread)
        return AfishaPost(message.message_id, is_caption=False)
    except TelegramAPIError as e:
        logger.warning("Failed to post afisha card: %s", e)
        return None


async def edit_afisha_card(
    bot: Bot, message_id: int, text: str, is_caption: bool = False
) -> bool:
    """Правка карточки в Афише (пометка «Прошло»/«Отменено»)."""
    if settings.group_chat_id is None:
        return False
    try:
        if is_caption:
            await bot.edit_message_caption(
                chat_id=settings.group_chat_id, message_id=message_id, caption=text
            )
        else:
            await bot.edit_message_text(
                text, chat_id=settings.group_chat_id, message_id=message_id
            )
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
