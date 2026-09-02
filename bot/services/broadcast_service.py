"""Рассылка в личку всем зарегистрированным.

Один механизм на две задачи: письмо владельца («✉️ Рассылка») и новость об
обновлении («📢 Обновления»). Отличаются они только текстом и тем, ложится ли
написанное в архив раздела; сама доставка общая — держать её в двух местах
значило бы чинить каждую беду дважды.

Telegram не даёт боту писать первым. Кто не запускал бота или закрыл ему
личку — сообщения не получит, и сделать с этим нельзя ничего. Это не сбой
рассылки: такой человек просто пропускается, а владельцу в конце называется,
скольким из скольких дошло.
"""

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User
from bot.db.repositories import audit_repo
from bot.enums import AuditAction, UserRole
from bot.services import content_service

logger = logging.getLogger(__name__)

SEND_PAUSE = 0.05  # пауза между личками, чтобы не упереться во флуд-лимит Telegram


async def recipients(session: AsyncSession) -> list[int]:
    """Кому уходит рассылка: все зарегистрированные, кроме забаненных.

    Забаненный остаётся в базе (чтобы не зарегистрировался заново), но бот с
    ним не разговаривает — и рассылка не исключение.
    """
    return list(
        await session.scalars(select(User.tg_id).where(User.current_role != UserRole.BANNED))
    )


async def _send_one(
    bot: Bot, tg_id: int, text: str, file_id: str | None, file_type: str | None
) -> None:
    """Одно сообщение: с файлом или без, с оглядкой на длину подписи."""
    if file_id is None:
        await bot.send_message(tg_id, text)
        return
    send = bot.send_photo if file_type == "photo" else bot.send_document
    if len(text) <= content_service.CAPTION_LIMIT:
        await send(tg_id, file_id, caption=text)
        return
    # В подпись текст не влез — тогда файл и текст идут отдельно. Иначе Telegram
    # обрежет сообщение молча, и человек прочитает половину.
    await send(tg_id, file_id)
    await bot.send_message(tg_id, text)


async def send_to_all(
    bot: Bot,
    tg_ids: list[int],
    text: str,
    file_id: str | None = None,
    file_type: str | None = None,
) -> int:
    """Отправляет сообщение каждому. Возвращает, скольким дошло."""
    delivered = 0
    for tg_id in tg_ids:
        try:
            await _send_one(bot, tg_id, text, file_id, file_type)
            delivered += 1
        except TelegramAPIError as e:
            logger.warning("Broadcast: failed to DM %s: %s", tg_id, e)
        await asyncio.sleep(SEND_PAUSE)
    return delivered


async def broadcast(
    session: AsyncSession,
    bot: Bot,
    owner: User,
    text: str,
    file_id: str | None,
    file_type: str | None,
) -> tuple[int, int]:
    """Письмо владельца всем. Возвращает (скольким доставлено, всего адресатов).

    Текст уходит ровно таким, каким его написали: никаких приписок бот не
    добавляет. Рассылка — не новость об обновлении, и в архив раздела она не
    ложится; след остаётся только в журнале действий.
    """
    await audit_repo.add(
        session,
        AuditAction.BROADCAST_SENT,
        actor_tg_id=owner.tg_id,
        meta={"has_file": file_id is not None, "length": len(text)},
    )
    await session.commit()

    tg_ids = await recipients(session)
    delivered = await send_to_all(bot, tg_ids, text, file_id, file_type)
    return delivered, len(tg_ids)
