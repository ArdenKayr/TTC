"""Живой список вузов (inline-режим Telegram).

Пользователь жмёт «🔍 Открыть список вузов» — открывается прокручиваемый
столбик всех вузов; по мере ввода названия неподходящие варианты исчезают
(поиск тот же, что и в анкете: терпимый к опечаткам и сокращениям).
Выбор отправляет в чат сообщение «🎓 <название>», которое ловит анкета.

Требует включённого inline-режима у @BotFather (/setinline).
"""

from aiogram import Router
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.db.repositories import university_repo

router = Router(name="inline_search")

PAGE_SIZE = 50  # столько вузов отдаём за раз; дальше Telegram сам попросит следующую страницу


@router.inline_query()
async def inline_university_search(query: InlineQuery, session: AsyncSession) -> None:
    text = query.query.strip()
    offset = int(query.offset) if query.offset.isdigit() else 0
    if text:
        universities = await university_repo.search(session, text, limit=20)
        next_offset = None
    else:
        universities = await university_repo.list_all(session, limit=PAGE_SIZE, offset=offset)
        next_offset = str(offset + PAGE_SIZE) if len(universities) == PAGE_SIZE else None
    results = [
        InlineQueryResultArticle(
            id=str(uni.university_id),
            title=uni.canonical_name,
            description=uni.city,
            input_message_content=InputTextMessageContent(
                message_text=texts.INLINE_PICK_PREFIX + uni.canonical_name
            ),
        )
        for uni in universities
    ]
    await query.answer(results, cache_time=5, is_personal=False, next_offset=next_offset)
