"""Сбор ошибок для владельца.

Любая необработанная ошибка в хендлере пишется в таблицу error_log
(тип апдейта, кто и что прислал, тип исключения, полный трейсбек)
и уходит владельцу в ЛС готовой карточкой — её достаточно переслать
разработчику. Сам обработчик ошибок не имеет права упасть: всё в
try/except с фолбэком в обычный лог.
"""

import logging
import traceback
from datetime import datetime, timezone
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ErrorEvent
from sqlalchemy import select

from bot import texts
from bot.db.base import async_session_factory
from bot.db.models import ErrorLog, User
from bot.enums import UserRole

logger = logging.getLogger(__name__)

_INPUT_LIMIT = 1000  # сколько символов ввода хранить в БД
_DM_TB_LIMIT = 2000  # сколько символов трейсбека помещается в карточку владельцу


def _describe_update(event: ErrorEvent) -> dict:
    """Что за апдейт сломал хендлер: тип, автор, чат, введённый текст."""
    info: dict = {"update_type": None, "user_tg_id": None, "chat_id": None, "input_text": None}
    upd = event.update
    message = upd.message or upd.edited_message
    if message is not None:
        info.update(
            update_type="message",
            user_tg_id=message.from_user.id if message.from_user else None,
            chat_id=message.chat.id,
            input_text=message.text or message.caption,
        )
    elif upd.callback_query is not None:
        cq = upd.callback_query
        info.update(
            update_type="callback_query",
            user_tg_id=cq.from_user.id,
            chat_id=cq.message.chat.id if cq.message is not None else None,
            input_text=cq.data,
        )
    else:
        try:
            info["update_type"] = upd.event_type
        except Exception:
            info["update_type"] = "unknown"
    return info


async def _record_and_notify(event: ErrorEvent, bot: Bot) -> None:
    exc = event.exception
    tb_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    info = _describe_update(event)
    input_text = (info["input_text"] or "").strip() or None
    if input_text is not None:
        input_text = input_text[:_INPUT_LIMIT]

    async with async_session_factory() as session:
        row = ErrorLog(
            update_type=info["update_type"],
            user_tg_id=info["user_tg_id"],
            chat_id=info["chat_id"],
            input_text=input_text,
            exception_type=type(exc).__name__,
            exception_message=str(exc) or "(без текста)",
            traceback_text=tb_text,
        )
        session.add(row)
        await session.commit()
        owner_ids = list(
            await session.scalars(select(User.tg_id).where(User.current_role == UserRole.OWNER))
        )

    dm = texts.ERROR_OWNER_DM.format(
        id=row.id,
        time=datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M:%S"),
        upd=info["update_type"] or "—",
        user=info["user_tg_id"] or "—",
        chat=info["chat_id"] or "—",
        input=escape((input_text or "—")[:200]),
        exc_type=escape(type(exc).__name__),
        exc_msg=escape((str(exc) or "(без текста)")[:500]),
        tb=escape(tb_text[-_DM_TB_LIMIT:]),
    )
    for owner_id in owner_ids:
        try:
            await bot.send_message(owner_id, dm)
        except TelegramAPIError as e:
            logger.warning("Failed to DM owner %s about error %s: %s", owner_id, row.id, e)


async def on_error(event: ErrorEvent, bot: Bot) -> bool:
    logger.exception("Unhandled error in handler", exc_info=event.exception)
    try:
        await _record_and_notify(event, bot)
    except Exception:
        logger.exception("Failed to record/notify about handler error")
    return True
