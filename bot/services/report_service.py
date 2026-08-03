"""Репорты: от жалобы до ответа её автору.

Раньше репорт был разовым сообщением в чат админов. Разобрать его можно было
только сразу, пока карточка не уехала вверх, а человек, который потратил время
на описание проблемы, не узнавал о ней больше ничего — ни что её увидели, ни
что починили. Молчание в ответ на жалобу читается как «всем всё равно».

Теперь у репорта есть номер, статус и переписка. Каждая смена статуса — повод
написать автору; тексты этих сообщений редактируются как обычные сценарии,
поэтому здесь их нет, здесь только решение, какой сценарий когда уходит.
"""

import logging
from datetime import datetime, timezone
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from bot import limits, texts
from bot.db.models import Report, ReportMessage, User
from bot.db.repositories import audit_repo, report_repo
from bot.enums import CLOSED_REPORT_STATUSES, AuditAction, ReportStatus
from bot.keyboards.report_kb import report_answer_kb, report_card_kb
from bot.services import notification_service, scenario_service

logger = logging.getLogger(__name__)

# Какое сообщение уходит автору на каждом переходе статуса.
STATUS_SCENARIO = {
    ReportStatus.IN_PROGRESS: "report_progress",
    ReportStatus.DONE: "report_done",
    ReportStatus.DECLINED: "report_declined",
}


def status_label(report: Report) -> str:
    return texts.REPORT_STATUS_LABELS[report.status.value]


def author_label(report: Report, author: User | None) -> str:
    """Кто прислал репорт. Автора могли удалить — тогда имя берём из снимка."""
    if author is None:
        return texts.REPORT_AUTHOR_DELETED.format(name=escape(report.author_name))
    username = f"@{author.username}" if author.username else f"id {author.tg_id}"
    return f"{escape(author.display_name)} ({username})"


def _short(text: str) -> str:
    if len(text) <= limits.REPORT_CARD_TALK_CHARS:
        return escape(text)
    return escape(text[: limits.REPORT_CARD_TALK_CHARS].rstrip()) + "…"


def card_text(report: Report, author: User | None, messages: list[ReportMessage]) -> str:
    """Карточка репорта: суть, статус и хвост переписки.

    Переписка показывается последними репликами, а не целиком: у карточки есть
    предел длины, а админу нужно понять, о чём уже говорили, — для этого хватает
    конца разговора.
    """
    card = texts.REPORT_CARD.format(
        number=report.report_id,
        status=status_label(report),
        author=author_label(report, author),
        text=escape(report.text),
    )
    if messages:
        shown = messages[-limits.REPORT_CARD_TALK_SHOWN :]
        hidden = len(messages) - len(shown)
        card += texts.REPORT_CARD_TALK_HEAD.format(count=len(messages))
        if hidden:
            card += texts.REPORT_CARD_TALK_MORE.format(count=hidden)
        for message in shown:
            template = (
                texts.REPORT_CARD_TALK_ADMIN
                if message.from_admin
                else texts.REPORT_CARD_TALK_AUTHOR
            )
            card += template.format(
                name=escape(message.author_name), text=_short(message.text)
            )
    return card


async def render_card(session: AsyncSession, report: Report) -> str:
    author = (
        await session.get(User, report.author_tg_id) if report.author_tg_id is not None else None
    )
    return card_text(report, author, await report_repo.messages(session, report.report_id))


async def refresh_card(session: AsyncSession, bot: Bot, report: Report) -> None:
    """Перерисовать карточку в админ-чате под текущий статус и переписку.

    Без этого в чате остаются карточки с устаревшим статусом и живыми кнопками:
    следующий админ жмёт «🔧 В работе» по уже закрытому репорту.
    """
    if report.card_message_id is None:
        return
    await notification_service.edit_admin_card(
        bot, report.card_message_id, await render_card(session, report), report_card_kb(report)
    )


async def open_report(session: AsyncSession, bot: Bot, author: User, text: str) -> Report:
    """Принять репорт: сохранить и показать админам карточку.

    Сохранение идёт до отправки карточки намеренно. Если Telegram не примет
    сообщение (чат недоступен, тема удалена), репорт всё равно останется
    в очереди раздела «🐞 Репорты» — потерять описание проблемы хуже, чем
    остаться без карточки в чате.
    """
    report = await report_repo.create(session, author.tg_id, author.display_name, text)
    await session.commit()
    try:
        report.card_message_id = await notification_service.send_admin_report(
            bot, await render_card(session, report), report_card_kb(report)
        )
        await session.commit()
    except TelegramAPIError as e:
        logger.warning("Report %s saved, but the admin card was not sent: %s", report.report_id, e)
    return report


async def change_status(
    session: AsyncSession, bot: Bot, report: Report, admin: User, status: ReportStatus
) -> scenario_service.Delivery:
    """Сменить статус и сказать об этом автору."""
    report.status = status
    report.taken_by = admin.tg_id
    report.updated_at = datetime.now(timezone.utc)
    await audit_repo.add(
        session,
        AuditAction.REPORT_STATUS_CHANGED,
        actor_tg_id=admin.tg_id,
        target_tg_id=report.author_tg_id,
        target_entity_type="report",
        target_entity_id=str(report.report_id),
        meta={"status": status.value},
    )
    await session.commit()
    # У закрытого репорта отвечать некому: кнопку «✍️ Ответить» не даём, чтобы
    # человек не писал в пустоту. Нужно что-то ещё — это новый репорт.
    keyboard = None if status in CLOSED_REPORT_STATUSES else report_answer_kb(report.report_id)
    delivery = await scenario_service.dm(
        bot,
        session,
        report.author_tg_id,
        STATUS_SCENARIO[status],
        number=report.report_id,
        reply_markup=keyboard,
    )
    await refresh_card(session, bot, report)
    return delivery


async def reply_to_author(
    session: AsyncSession, bot: Bot, report: Report, admin: User, text: str
) -> scenario_service.Delivery:
    """Ответ админа автору репорта — в личку и в переписку."""
    await report_repo.add_message(
        session,
        report,
        from_admin=True,
        author_tg_id=admin.tg_id,
        author_name=admin.display_name,
        text=text,
    )
    report.updated_at = datetime.now(timezone.utc)
    await audit_repo.add(
        session,
        AuditAction.REPORT_ANSWERED,
        actor_tg_id=admin.tg_id,
        target_tg_id=report.author_tg_id,
        target_entity_type="report",
        target_entity_id=str(report.report_id),
    )
    await session.commit()
    delivery = await scenario_service.dm(
        bot,
        session,
        report.author_tg_id,
        "report_reply",
        number=report.report_id,
        text=escape(text),
        reply_markup=report_answer_kb(report.report_id),
    )
    await refresh_card(session, bot, report)
    return delivery


async def answer_from_author(
    session: AsyncSession, bot: Bot, report: Report, author: User, text: str
) -> None:
    """Ответ автора админам: в переписку, в карточку и заметкой в тему репортов."""
    await report_repo.add_message(
        session,
        report,
        from_admin=False,
        author_tg_id=author.tg_id,
        author_name=author.display_name,
        text=text,
    )
    report.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await refresh_card(session, bot, report)
    # Карточку правим молча — она не всплывёт в чате, и ответ остался бы
    # незамеченным. Поэтому о нём говорим отдельным сообщением в теме.
    try:
        await notification_service.send_admin_report(
            bot,
            texts.REPORT_ANSWER_IN_CHAT.format(
                number=report.report_id,
                name=escape(author.display_name),
                text=escape(text),
            ),
        )
    except TelegramAPIError as e:
        logger.warning("Report %s: the author's answer was not posted: %s", report.report_id, e)
