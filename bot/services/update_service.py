"""«Обновления»: владелец публикует новость — она уходит в личку всем
зарегистрированным и встаёт сверху раздела «Информация → Обновления»
(старое содержимое остаётся ниже как архив, с обрезкой по длине)."""

import logging
from datetime import datetime, timezone

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.db.models import User
from bot.db.repositories import audit_repo, content_repo
from bot.enums import AuditAction
from bot.services import broadcast_service

logger = logging.getLogger(__name__)

_ARCHIVE_LIMIT = 3800  # чтобы раздел «Обновления» всегда влезал в одно сообщение


def build_entry(text: str) -> str:
    """Запись обновления — то, что ложится в архив раздела «Обновления»."""
    date_str = datetime.now(timezone.utc).strftime("%d.%m.%Y")
    return texts.UPD_ENTRY_HEADER.format(date=date_str) + text


def build_broadcast(entry: str) -> str:
    """То же, но для личного сообщения: с припиской, где искать раздел.

    В архив приписка не идёт — там она повторялась бы у каждой записи, хотя
    человек и так уже стоит в этом разделе, когда его читает.
    """
    return entry + texts.UPD_ENTRY_FOOTER.format(
        info=texts.BTN.INFO, updates=texts.BTN.INFO_UPDATES
    )


async def publish_update(
    session: AsyncSession,
    bot: Bot,
    owner: User,
    text: str,
    file_id: str | None,
    file_type: str | None,
) -> tuple[int, int]:
    """Публикует обновление. Возвращает (скольким доставлено, всего получателей)."""
    entry = build_entry(text)

    block = await content_repo.get_or_create(session, "updates")
    old = (block.text or "").strip()
    combined = entry if not old or old == texts.UPDATES_DEFAULT else entry + texts.UPD_ARCHIVE_SEP + old
    if len(combined) > _ARCHIVE_LIMIT:
        combined = combined[: _ARCHIVE_LIMIT - 1] + "…"
    block.text = combined
    if file_id is not None:
        block.file_id = file_id
        block.file_type = file_type
    block.updated_by = owner.tg_id
    await audit_repo.add(
        session,
        AuditAction.UPDATE_PUBLISHED,
        actor_tg_id=owner.tg_id,
        target_entity_type="content_block",
        target_entity_id="updates",
        meta={"has_file": file_id is not None, "length": len(text)},
    )
    await session.commit()

    tg_ids = await broadcast_service.recipients(session)
    message = build_broadcast(entry)
    delivered = await broadcast_service.send_to_all(bot, tg_ids, message, file_id, file_type)
    return delivered, len(tg_ids)
