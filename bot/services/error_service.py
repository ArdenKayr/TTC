"""Сбор ошибок и «мягких сбоев» для владельца.

Два входа в один и тот же журнал (таблица error_log) и одну и ту же
карточку владельцу в ЛС:

- `on_error` — настоящий крэш: необработанное исключение в хендлере
  (полный трейсбек, тип и текст исключения).
- `report_issue` — функция НЕ упала, но результат не тот, что задуман
  (не удалось создать инвайт-ссылку, не доставилась личка, не удалось
  исключить забаненного из группы и т.п.). Раньше такие случаи в лучшем
  случае мелькали строкой в карточке решающего админа и терялись
  навсегда; теперь они пишутся в тот же журнал, что и крэши, и владелец
  получает такую же карточку.

Обе функции никогда не имеют права упасть сами: всё в try/except
с фолбэком в обычный лог.
"""

import logging
import traceback
from datetime import datetime, timezone
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ErrorEvent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.db.base import async_session_factory
from bot.db.models import ErrorLog, User
from bot.db.repositories import user_repo
from bot.enums import UserRole

logger = logging.getLogger(__name__)

_INPUT_LIMIT = 1000  # сколько символов ввода/контекста хранить в БД
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


def format_person(tg_id: int | None, labels: dict[int, str]) -> str:
    """Число превращается в «Имя (@ник), id 123» — если человек есть в базе."""
    if tg_id is None:
        return "—"
    label = labels.get(tg_id)
    return f"{label}, id {tg_id}" if label else f"id {tg_id} (не в базе)"


async def _persist_and_notify(
    bot: Bot,
    *,
    update_type: str | None,
    user_tg_id: int | None,
    chat_id: int | None,
    input_text: str | None,
    exception_type: str,
    exception_message: str,
    traceback_text: str,
) -> None:
    if input_text is not None:
        input_text = input_text.strip()[:_INPUT_LIMIT] or None

    async with async_session_factory() as session:
        row = ErrorLog(
            update_type=update_type,
            user_tg_id=user_tg_id,
            chat_id=chat_id,
            input_text=input_text,
            exception_type=exception_type,
            exception_message=exception_message,
            traceback_text=traceback_text,
        )
        session.add(row)
        await session.commit()
        owner_ids = list(
            await session.scalars(select(User.tg_id).where(User.current_role == UserRole.OWNER))
        )
        labels = await user_repo.label_map(session, {user_tg_id} if user_tg_id else set())

    dm = texts.ERROR_OWNER_DM.format(
        id=row.id,
        time=datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M:%S"),
        upd=update_type or "—",
        user=escape(format_person(user_tg_id, labels)),
        chat=chat_id or "—",
        input=escape((input_text or "—")[:200]),
        exc_type=escape(exception_type),
        exc_msg=escape(exception_message[:500]),
        tb=escape(traceback_text[-_DM_TB_LIMIT:]),
    )
    for owner_id in owner_ids:
        try:
            await bot.send_message(owner_id, dm)
        except TelegramAPIError as e:
            logger.warning("Failed to DM owner %s about error %s: %s", owner_id, row.id, e)


async def on_error(event: ErrorEvent, bot: Bot) -> bool:
    """Настоящий крэш — необработанное исключение в хендлере."""
    logger.exception("Unhandled error in handler", exc_info=event.exception)
    try:
        exc = event.exception
        tb_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        info = _describe_update(event)
        await _persist_and_notify(
            bot,
            update_type=info["update_type"],
            user_tg_id=info["user_tg_id"],
            chat_id=info["chat_id"],
            input_text=info["input_text"],
            exception_type=type(exc).__name__,
            exception_message=str(exc) or "(без текста)",
            traceback_text=tb_text,
        )
    except Exception:
        logger.exception("Failed to record/notify about handler error")
    return True


async def report_issue(
    bot: Bot,
    *,
    source: str,
    note: str,
    tg_id: int | None = None,
    chat_id: int | None = None,
    context: str | None = None,
) -> None:
    """Мягкий сбой: код не упал, но результат не тот, что задуман.

    `source` — что за операция («Регистрация: одобрение», «Бан» и т.п.),
    `note` — что конкретно не задалось, `tg_id` — кого это касалось.
    Пишется в тот же error_log (с пометкой ⚠ вместо имени исключения) и
    уходит владельцу той же карточкой — просмотреть можно в «Логи → Ошибки»
    или в CRUD → «Логи ошибок».
    """
    try:
        await _persist_and_notify(
            bot,
            update_type="issue",
            user_tg_id=tg_id,
            chat_id=chat_id,
            input_text=context,
            exception_type=f"⚠ {source}",
            exception_message=note,
            traceback_text="(без трейсбека — операция не упала, а отработала не так, как задумано)",
        )
    except Exception:
        logger.exception("Failed to report issue: source=%s note=%s", source, note)
