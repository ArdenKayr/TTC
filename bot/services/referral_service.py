"""Ссылки-приглашения: кто из админов сколько людей привёл.

Ссылка — это обычная ссылка на бота с хвостом: `t.me/бот?start=код`. Telegram
передаёт этот хвост боту первым же сообщением, человек ничего не замечает и
видит привычное приветствие. Бот в этот момент запоминает, по чьей ссылке он
пришёл, и потом отмечает две вехи: отправил анкету, приняли в сообщество.

Считается человек, а не нажатие: повторные `/start` по той же ссылке ничего не
прибавляют, а первая ссылка не перебивается второй (подробнее — в описании
модели `ReferralVisit`). Свою собственную ссылку админ открыть может, но себе
её не засчитает.
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone
from html import escape

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.db.models import ReferralLink, User
from bot.db.repositories import referral_repo, user_repo
from bot.enums import UserRole

# Буквы и цифры, которые не путаются на слух и на глаз: ни «о» с нулём, ни «l»
# с единицей. Код диктуют голосом и переписывают руками.
_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
CODE_LENGTH = 7

# Что вообще может быть кодом ссылки: Telegram разрешает в хвосте `?start=`
# только латиницу, цифры, дефис и подчёркивание. Всё прочее — не наша ссылка,
# а чужая рассылка или опечатка, и в базу за этим ходить незачем.
PAYLOAD_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(CODE_LENGTH))


async def unique_code(session: AsyncSession) -> str:
    """Код, которого ещё нет в базе.

    Совпадение при таком алфавите маловероятно, но ссылка с чужим кодом
    засчитывала бы переходы не тому человеку, поэтому проверяем.
    """
    for _ in range(10):
        code = new_code()
        if await referral_repo.get_link(session, code) is None:
            return code
    raise RuntimeError("Не удалось подобрать свободный код ссылки-приглашения")


async def link_url(bot: Bot, code: str) -> str:
    """Готовая ссылка на бота. Имя бота спрашиваем у Telegram (оно кешируется)."""
    me = await bot.me()
    return f"https://t.me/{me.username}?start={code}"


async def note_start(
    session: AsyncSession, *, tg_id: int, payload: str, is_registered: bool
) -> ReferralLink | None:
    """Учитывает переход по ссылке. Возвращает ссылку, если переход засчитан.

    Не засчитывается: мусор вместо кода, неизвестный код, уже зарегистрированный
    человек (его приводить некуда), владелец ссылки и тот, кто уже числится за
    какой-то ссылкой.
    """
    if not payload or not PAYLOAD_RE.match(payload):
        return None
    if is_registered:
        return None
    link = await referral_repo.get_link(session, payload)
    if link is None or link.owner_tg_id == tg_id:
        return None
    visit = await referral_repo.add_visit(session, code=link.code, tg_id=tg_id)
    if visit is None:
        return None
    await session.commit()
    return link


async def note_applied(session: AsyncSession, tg_id: int) -> None:
    """Человек отправил анкету. Коммит делает вызывающий код."""
    await referral_repo.mark_applied(session, tg_id, _utcnow())


async def note_approved(session: AsyncSession, tg_id: int) -> None:
    """Заявку приняли — человек дошёл до сообщества. Коммит делает вызывающий код."""
    await referral_repo.mark_approved(session, tg_id, _utcnow())


async def render_links(
    session: AsyncSession, bot: Bot, links: list[ReferralLink], *, with_owner: bool
) -> list[tuple[ReferralLink, str]]:
    """Готовые карточки ссылок: по одной на ссылку, вместе с их счётчиками.

    `with_owner` — показывать ли строку «Чья»: владельцу и суперадмину видны
    ссылки всех админов, и без имени они не отличаются друг от друга.
    """
    counters = await referral_repo.stats(session, [link.code for link in links])
    owners: dict[int, str] = {}
    if with_owner:
        owners = await user_repo.label_map(
            session, {link.owner_tg_id for link in links if link.owner_tg_id is not None}
        )

    cards: list[tuple[ReferralLink, str]] = []
    for link in links:
        visits, applied, approved = counters.get(link.code, (0, 0, 0))
        card = texts.REF_CARD.format(
            title=escape(link.title),
            url=await link_url(bot, link.code),
            visits=visits,
            applied=applied,
            approved=approved,
        )
        if with_owner:
            # Хозяин ссылки мог удалить аккаунт: ссылка и её цифры остались, а
            # приписывать их некому — так и говорим, вместо голого номера.
            owner = owners.get(link.owner_tg_id) if link.owner_tg_id is not None else None
            card += (
                texts.REF_CARD_OWNER.format(owner=escape(owner))
                if owner is not None
                else texts.REF_CARD_OWNER_GONE
            )
        cards.append((link, card))
    return cards


def may_see_all(user: User) -> bool:
    """Чужие ссылки видит и раздаёт тот, кто отвечает за набор целиком.

    Обычному админу своя статистика нужна для себя, а чужая превращает набор в
    соревнование, которого никто не объявлял.
    """
    return user.current_role in (UserRole.SUPERADMIN, UserRole.OWNER)


def may_delete(user: User, link: ReferralLink) -> bool:
    """Свою ссылку хозяин убирает когда захочет, чужую — только суперадмин.

    Удаление уносит и счётчики, поэтому чужие ссылки закрыты даже от соседа с
    такими же правами: цифры чужой работы стирать не ему. Ссылку, оставшуюся
    без хозяина (он удалил аккаунт), убирает суперадмин или владелец.
    """
    return link.owner_tg_id == user.tg_id or may_see_all(user)
