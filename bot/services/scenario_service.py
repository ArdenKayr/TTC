"""Сценарии: тексты-реакции бота, редактируемые суперадминами без кода.

Каждый сценарий — сообщение, которое бот отправляет в ответ на действие
(решение по заявке, бан, репорт…). Изменённый текст и вложение хранятся
в content_blocks под ключом ``scen_<key>``; пока админы ничего не меняли,
действует стандартный текст из texts.py. Плейсхолдеры вида ``{title}``
бот подставляет сам; неизвестные плейсхолдеры остаются как есть, а текст
со сломанными скобками откатывается к стандартному — сообщение уйдёт
в любом случае.
"""

import logging
import re
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup, Message, ReplyKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.db.models import User
from bot.db.repositories import audit_repo, content_repo
from bot.enums import AuditAction
from bot.services import content_service
from bot.services.content_service import Content

logger = logging.getLogger(__name__)

_SLOT_PREFIX = "scen_"


@dataclass(frozen=True)
class Scenario:
    key: str
    title: str
    group: str
    default: str
    params: tuple[str, ...] = ()


G_REG = "Регистрация"
G_ACT = "Мероприятия и голосования"
G_PROFILE = "Профиль и репорты"
G_BAN = "Баны"

GROUPS = (G_REG, G_ACT, G_PROFILE, G_BAN)

_LIST = [
    Scenario("reg_submitted", "Заявка на регистрацию отправлена", G_REG, texts.REG_SUBMITTED),
    Scenario(
        "reg_submitted_two_step",
        "Заявка отправлена (с новым вузом)",
        G_REG,
        texts.REG_SUBMITTED_TWO_STEP,
    ),
    Scenario(
        "reg_approved",
        "Регистрация одобрена (инвайт-ссылку бот добавит сам)",
        G_REG,
        texts.APPROVED_DM,
    ),
    Scenario(
        "reg_rejected",
        "Регистрация отклонена (причину и таймаут бот добавит сам)",
        G_REG,
        texts.REJECTED_DM,
    ),
    Scenario("act_sent", "Заявка на мероприятие отправлена", G_ACT, texts.ACT_SENT),
    Scenario(
        "act_approved",
        "Мероприятие одобрено (автор стал организатором)",
        G_ACT,
        texts.ACT_APPROVED_DM,
        ("title",),
    ),
    Scenario(
        "act_approved_org",
        "Мероприятие одобрено (автор уже организатор)",
        G_ACT,
        texts.ACT_APPROVED_DM_ALREADY_ORG,
        ("title",),
    ),
    Scenario("act_rejected", "Мероприятие отклонено", G_ACT, texts.ACT_REJECTED_DM, ("title",)),
    Scenario(
        "act_completed", "Мероприятие завершено", G_ACT, texts.ACT_COMPLETED_DM, ("title",)
    ),
    Scenario(
        "act_cancelled", "Мероприятие отменено админами", G_ACT, texts.ACT_CANCELLED_DM, ("title",)
    ),
    Scenario("org_demoted", "Роль организатора снята", G_ACT, texts.ORG_DEMOTED_DM),
    Scenario("vote_sent", "Заявка на голосование отправлена", G_ACT, texts.VOTE_SENT),
    Scenario(
        "vote_approved",
        "Голосование опубликовано",
        G_ACT,
        texts.VOTE_APPROVED_DM,
        ("question",),
    ),
    Scenario(
        "vote_rejected",
        "Голосование отклонено",
        G_ACT,
        texts.VOTE_REJECTED_DM,
        ("question",),
    ),
    Scenario("report_sent", "Репорт принят", G_PROFILE, texts.REPORT_SENT),
    Scenario("profile_updated", "Профиль обновлён", G_PROFILE, texts.PROFILE_UPDATED),
    Scenario("profile_deleted", "Аккаунт удалён", G_PROFILE, texts.PROFILE_DELETED),
    Scenario(
        "ban_target", "Бан: сообщение забаненному (ЛС)", G_BAN, texts.BAN_TARGET_DM_DEFAULT
    ),
    Scenario(
        "unban_target", "Разбан: сообщение разбаненному (ЛС)", G_BAN, texts.UNBAN_TARGET_DM_DEFAULT
    ),
    Scenario(
        "banned_guard",
        "Ответ забаненному, который пишет боту",
        G_BAN,
        texts.BANNED_DM,
    ),
    Scenario(
        "ban_done",
        "Бан: подтверждение админу (актору)",
        G_BAN,
        texts.BAN_DONE,
        ("name", "tg_id"),
    ),
]
SCENARIOS: dict[str, Scenario] = {s.key: s for s in _LIST}


class _SafeParams(dict):
    """format_map-словарь: неизвестный плейсхолдер остаётся в тексте как есть."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def validate_template(text: str) -> bool:
    try:
        text.format_map(_SafeParams())
    except (ValueError, IndexError, KeyError):
        return False
    return True


# Оформление, попавшее ВНУТРЬ подстановки: {<b>title</b>} вместо <b>{title}</b>.
_SPLIT_PLACEHOLDER = re.compile(r"\{[^{}]*<[^{}]*\}")


def has_split_placeholder(text: str) -> bool:
    """Подстановка разорвана оформлением — бот не сможет её подставить.

    Легко получить случайно: админ выделяет жирным слово вместе с одной из
    фигурных скобок. Формально текст остаётся корректным (проверка скобок
    проходит), но имя подстановки превращается из ``title`` в ``<b>title</b>``,
    и вместо названия мероприятия человек увидит сырое ``{<b>title</b>}``.
    Поэтому такой текст не принимаем.
    """
    return _SPLIT_PLACEHOLDER.search(text) is not None


async def raw(session: AsyncSession, key: str) -> tuple[Content, bool]:
    """Шаблон как он хранится (без подстановок) + флаг «изменён админами»."""
    scen = SCENARIOS[key]
    block = await content_repo.get(session, _SLOT_PREFIX + key)
    if block is None:
        return Content(scen.default, None, None), False
    customized = bool(block.text) or block.file_id is not None
    return Content(block.text or scen.default, block.file_id, block.file_type), customized


async def render(session: AsyncSession, key: str, **params) -> Content:
    content, _ = await raw(session, key)
    text = content.text
    try:
        text = text.format_map(_SafeParams(params))
    except (ValueError, IndexError, KeyError):
        text = SCENARIOS[key].default.format_map(_SafeParams(params))
    return Content(text, content.file_id, content.file_type)


async def dm(
    bot: Bot, session: AsyncSession, tg_id: int, key: str, *, suffix: str = "", **params
) -> bool:
    """Сообщение сценария в ЛС. False — если Telegram не дал отправить."""
    content = await render(session, key, **params)
    text = content.text + suffix
    try:
        if content.file_id is None:
            await bot.send_message(tg_id, text)
        else:
            send = bot.send_photo if content.file_type == "photo" else bot.send_document
            if len(text) <= content_service.CAPTION_LIMIT:
                await send(tg_id, content.file_id, caption=text)
            else:
                await send(tg_id, content.file_id)
                await bot.send_message(tg_id, text)
        return True
    except TelegramAPIError as e:
        logger.warning("Failed to DM user %s (scenario %s): %s", tg_id, key, e)
        return False


async def reply(
    message: Message,
    session: AsyncSession,
    key: str,
    keyboard: InlineKeyboardMarkup | ReplyKeyboardMarkup | None = None,
    *,
    suffix: str = "",
    **params,
) -> None:
    """Сообщение сценария в тот же чат (ответ на действие пользователя)."""
    content = await render(session, key, **params)
    if suffix:
        content = Content(content.text + suffix, content.file_id, content.file_type)
    await content_service.send_content(message, content, keyboard)


# --- Редактирование (использует те же content_blocks, что и /content) ---


async def set_text(session: AsyncSession, actor: User, key: str, text: str) -> None:
    await content_service.update_text(session, actor, _SLOT_PREFIX + key, text)


async def set_file(
    session: AsyncSession, actor: User, key: str, file_id: str, file_type: str, caption: str | None
) -> None:
    await content_service.update_file(session, actor, _SLOT_PREFIX + key, file_id, file_type, caption)


async def remove_file(session: AsyncSession, actor: User, key: str) -> None:
    await content_service.remove_file(session, actor, _SLOT_PREFIX + key)


async def reset(session: AsyncSession, actor: User, key: str) -> None:
    block = await content_repo.get(session, _SLOT_PREFIX + key)
    if block is None:
        return
    await session.delete(block)
    await audit_repo.add(
        session,
        AuditAction.CONTENT_UPDATED,
        actor_tg_id=actor.tg_id,
        target_entity_type="content_block",
        target_entity_id=_SLOT_PREFIX + key,
        meta={"changed": "reset_to_default"},
    )
    await session.commit()
