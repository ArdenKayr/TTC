from dataclasses import dataclass

from aiogram.types import InlineKeyboardMarkup, Message, ReplyKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.db.models import User
from bot.db.repositories import audit_repo, content_repo
from bot.enums import AuditAction

CAPTION_LIMIT = 1024  # Telegram: подпись к файлу не длиннее 1024 символов


@dataclass(frozen=True)
class Slot:
    key: str
    title: str
    default_text: str


# Слоты контента, который админы могут менять через /content.
# Новый слот = новая строка здесь + текст по умолчанию в texts.py.
SLOTS: dict[str, Slot] = {
    "welcome": Slot("welcome", "Приветствие при запуске бота", texts.WELCOME_DEFAULT),
    "about": Slot("about", "«Кто мы?» — рассказ о сообществе", texts.ABOUT_DEFAULT),
    "rules": Slot("rules", "Правила сообщества", texts.RULES_DEFAULT),
    "docs": Slot("docs", "Документы", texts.DOCS_DEFAULT),
    "updates": Slot("updates", "Обновления + архив", texts.UPDATES_DEFAULT),
    "become_organizer": Slot("become_organizer", "Как стать организатором", texts.BECOME_ORG_DEFAULT),
    "become_admin": Slot("become_admin", "Как стать админом", texts.BECOME_ADMIN_DEFAULT),
    "admin_regulations": Slot(
        "admin_regulations", "Админские регламенты (видят только суперадмины)", texts.ADMIN_REGS_DEFAULT
    ),
}


@dataclass(frozen=True)
class Content:
    text: str
    file_id: str | None
    file_type: str | None


async def get_content(session: AsyncSession, slot_key: str) -> Content:
    slot = SLOTS[slot_key]
    block = await content_repo.get(session, slot_key)
    if block is None:
        return Content(slot.default_text, None, None)
    return Content(block.text or slot.default_text, block.file_id, block.file_type)


async def send_content(
    message: Message,
    content: Content,
    keyboard: InlineKeyboardMarkup | ReplyKeyboardMarkup | None = None,
) -> None:
    """Отправляет контент в тот же чат: файл с подписью или просто текст."""
    if content.file_id is None:
        await message.answer(content.text, reply_markup=keyboard)
        return
    caption = content.text if len(content.text) <= CAPTION_LIMIT else None
    if content.file_type == "photo":
        await message.answer_photo(content.file_id, caption=caption, reply_markup=keyboard)
    else:
        await message.answer_document(content.file_id, caption=caption, reply_markup=keyboard)
    if caption is None:
        await message.answer(content.text, reply_markup=keyboard)


async def update_text(session: AsyncSession, actor: User, slot_key: str, text: str) -> None:
    block = await content_repo.get_or_create(session, slot_key)
    block.text = text
    block.updated_by = actor.tg_id
    await audit_repo.add(
        session,
        AuditAction.CONTENT_UPDATED,
        actor_tg_id=actor.tg_id,
        target_entity_type="content_block",
        target_entity_id=slot_key,
        meta={"changed": "text"},
    )
    await session.commit()


async def update_file(
    session: AsyncSession,
    actor: User,
    slot_key: str,
    file_id: str,
    file_type: str,
    caption: str | None,
) -> None:
    block = await content_repo.get_or_create(session, slot_key)
    block.file_id = file_id
    block.file_type = file_type
    if caption:
        block.text = caption
    block.updated_by = actor.tg_id
    await audit_repo.add(
        session,
        AuditAction.CONTENT_UPDATED,
        actor_tg_id=actor.tg_id,
        target_entity_type="content_block",
        target_entity_id=slot_key,
        meta={"changed": "file", "file_type": file_type, "caption_updated": bool(caption)},
    )
    await session.commit()


async def remove_file(session: AsyncSession, actor: User, slot_key: str) -> None:
    block = await content_repo.get_or_create(session, slot_key)
    block.file_id = None
    block.file_type = None
    block.updated_by = actor.tg_id
    await audit_repo.add(
        session,
        AuditAction.CONTENT_UPDATED,
        actor_tg_id=actor.tg_id,
        target_entity_type="content_block",
        target_entity_id=slot_key,
        meta={"changed": "file_removed"},
    )
    await session.commit()
