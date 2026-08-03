"""Панель владельца: «Логи» (по темам и периодам) и «Обновления» (рассылка).

Логи: тема (ошибки / CRUD / контент / люди и роли / мероприятия / вузы / всё)
→ период (сутки / неделя / месяц / всё время) → последние записи. Ошибки
берутся из error_log, остальное — из audit_log по типам действий.
"""

import json
from datetime import datetime, timedelta, timezone
from html import escape

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.db.models import ErrorLog, User
from bot.db.repositories import audit_repo, user_repo
from bot.enums import AuditAction as _A
from bot.filters.role_filter import IsOwner
from bot.keyboards.callback_data import LogCB, UpdatePostCB
from bot.keyboards.common_kb import MENU_BUTTON_TEXTS as _MENU_BUTTONS
from bot.routers.common import send_start_screen
from bot.services import content_service, update_service
from bot.services.error_service import format_person
from bot.states.content_states import UpdatePostForm

router = Router(name="owner_panel")
router.message.filter(IsOwner())
router.callback_query.filter(IsOwner())

_PRIVATE = F.chat.type == ChatType.PRIVATE

_LOG_LIMIT = 25

# Темы логов: ключ → (название, типы действий аудита). "err" — особая тема
# (таблица error_log), None вместо списка — все действия аудита.
LOG_CATS: dict[str, tuple[str, tuple[str, ...] | None]] = {
    "err": ("🐞 Ошибки", None),
    "crud": (
        "🗄 База данных (CRUD)",
        (_A.CRUD_CREATED.value, _A.CRUD_UPDATED.value, _A.CRUD_DELETED.value),
    ),
    "content": (
        "📄 Контент и сценарии",
        (_A.CONTENT_UPDATED.value, _A.UPDATE_PUBLISHED.value),
    ),
    "people": (
        "👥 Люди и роли",
        (
            _A.REGISTRATION_APPROVED.value,
            _A.REGISTRATION_REJECTED.value,
            _A.ROLE_CHANGED.value,
            _A.USER_BANNED.value,
            _A.USER_UNBANNED.value,
            _A.USER_PERMISSIONS_CHANGED.value,
            _A.PERM_GROUP_CREATED.value,
            _A.PERM_GROUP_UPDATED.value,
            _A.PERM_GROUP_DELETED.value,
            _A.PROFILE_UPDATED.value,
            _A.ACCOUNT_DELETED.value,
        ),
    ),
    "acts": (
        "📅 Мероприятия и голосования",
        (
            _A.ACTIVITY_APPROVED.value,
            _A.ACTIVITY_REJECTED.value,
            _A.ACTIVITY_COMPLETED.value,
            _A.ACTIVITY_CANCELLED.value,
            _A.VOTE_APPROVED.value,
            _A.VOTE_REJECTED.value,
            _A.ORGANIZER_PROMOTED.value,
            _A.ORGANIZER_DEMOTED.value,
        ),
    ),
    "uni": (
        "🏛 Вузы",
        (
            _A.UNIVERSITY_ADDED.value,
            _A.UNIVERSITY_REQUEST_APPROVED.value,
            _A.UNIVERSITY_REQUEST_REJECTED.value,
            _A.UNIVERSITY_REQUEST_EDITED.value,
            _A.ALIAS_APPROVED.value,
            _A.ALIAS_REJECTED.value,
            _A.ALIAS_EDITED.value,
        ),
    ),
    "all": ("📜 Всё подряд", None),
}

_PERIODS = (
    (1, texts.BTN.LOGS_DAY, "за сутки"),
    (7, texts.BTN.LOGS_WEEK, "за неделю"),
    (30, texts.BTN.LOGS_MONTH, "за месяц"),
    (0, texts.BTN.LOGS_ALL, "за всё время"),
)
_PERIOD_LABELS = {days: label for days, _, label in _PERIODS}


def _cats_kb() -> InlineKeyboardMarkup:
    rows = []
    row: list[InlineKeyboardButton] = []
    for key, (title, _actions) in LOG_CATS.items():
        row.append(InlineKeyboardButton(text=title, callback_data=LogCB(cat=key).pack()))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _periods_kb(cat: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=btn, callback_data=LogCB(cat=cat, days=days).pack()
                )
                for days, btn, _label in _PERIODS[:2]
            ],
            [
                InlineKeyboardButton(
                    text=btn, callback_data=LogCB(cat=cat, days=days).pack()
                )
                for days, btn, _label in _PERIODS[2:]
            ],
            [InlineKeyboardButton(text=texts.BTN.LOGS_BACK, callback_data=LogCB(cat="home").pack())],
        ]
    )


def _audit_line(row, labels: dict[int, str]) -> str:
    label = texts.AUDIT_ACTION_LABELS.get(row.action_type, row.action_type)
    actor = (
        escape(format_person(row.actor_tg_id, labels))
        if row.actor_tg_id
        else texts.LOGS_ACTOR_SYSTEM
    )
    if row.target_tg_id:
        target = escape(format_person(row.target_tg_id, labels))
    elif row.target_entity_id:
        target = escape(str(row.target_entity_id))
    else:
        target = None
    line = f"{row.created_at:%d.%m %H:%M} · <b>{escape(label)}</b> · {actor}"
    if target:
        line += f" → {target}"
    if row.reason:
        line += f" ({escape(row.reason[:40])})"
    elif row.meta:
        line += f" · {escape(json.dumps(row.meta, ensure_ascii=False)[:60])}"
    return line


def _error_line(row: ErrorLog, labels: dict[int, str]) -> str:
    who = f" · {escape(format_person(row.user_tg_id, labels))}" if row.user_tg_id else ""
    return (
        f"№{row.id} {row.occurred_at:%d.%m %H:%M} · <b>{escape(row.exception_type)}</b>: "
        f"{escape(row.exception_message[:60])}{who}"
    )


async def _render_logs(session: AsyncSession, cat: str, days: int) -> str:
    title, actions = LOG_CATS[cat]
    period = _PERIOD_LABELS.get(days, "за всё время")
    since = datetime.now(timezone.utc) - timedelta(days=days) if days > 0 else None

    if cat == "err":
        query = select(ErrorLog)
        if since is not None:
            query = query.where(ErrorLog.occurred_at >= since)
        total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = list(
            await session.scalars(query.order_by(ErrorLog.occurred_at.desc()).limit(_LOG_LIMIT))
        )
        labels = await user_repo.label_map(session, {r.user_tg_id for r in rows if r.user_tg_id})
        lines = [_error_line(r, labels) for r in rows]
        footer = texts.LOGS_ERR_FOOTER if rows else ""
    else:
        rows, total = await audit_repo.list_recent(
            session, actions=actions, since=since, limit=_LOG_LIMIT
        )
        ids = {r.actor_tg_id for r in rows if r.actor_tg_id} | {
            r.target_tg_id for r in rows if r.target_tg_id
        }
        labels = await user_repo.label_map(session, ids)
        lines = [_audit_line(r, labels) for r in rows]
        footer = ""

    if not rows:
        return texts.LOGS_EMPTY.format(cat=title, period=period)
    suffix = texts.LOGS_SHOWN_SUFFIX.format(shown=len(rows)) if total > len(rows) else ""
    text = texts.LOGS_HEADER.format(cat=title, period=period, total=total, suffix=suffix)
    text += "\n".join(lines) + footer
    return text if len(text) <= 4000 else text[:3999] + "…"


# --- Логи ---


@router.message(_PRIVATE, StateFilter(None), F.text == texts.BTN.ADMIN_PANEL_LOGS)
async def logs_home(message: Message) -> None:
    await message.answer(texts.LOGS_PICK_CAT, reply_markup=_cats_kb())


@router.callback_query(LogCB.filter())
async def cb_logs(
    callback: CallbackQuery, callback_data: LogCB, session: AsyncSession
) -> None:
    if callback_data.cat == "home":
        await callback.message.edit_text(texts.LOGS_PICK_CAT, reply_markup=_cats_kb())
        await callback.answer()
        return
    if callback_data.cat not in LOG_CATS:
        await callback.answer()
        return
    if callback_data.days < 0:
        title = LOG_CATS[callback_data.cat][0]
        await callback.message.edit_text(
            texts.LOGS_PICK_PERIOD.format(cat=title),
            reply_markup=_periods_kb(callback_data.cat),
        )
        await callback.answer()
        return
    text = await _render_logs(session, callback_data.cat, callback_data.days)
    try:
        await callback.message.edit_text(text, reply_markup=_periods_kb(callback_data.cat))
    except Exception:  # текст не изменился — Telegram не даёт править без изменений
        pass
    await callback.answer()


# --- Обновления ---


@router.message(_PRIVATE, StateFilter(None), F.text == texts.BTN.ADMIN_PANEL_UPDATES)
async def update_start(message: Message, state: FSMContext) -> None:
    await state.set_state(UpdatePostForm.waiting)
    await message.answer(
        texts.UPD_PROMPT,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=texts.BTN.CONTENT_CANCEL,
                        callback_data=UpdatePostCB(action="cancel").pack(),
                    )
                ]
            ]
        ),
    )


@router.message(StateFilter(UpdatePostForm), F.text.in_(_MENU_BUTTONS))
async def update_menu_pressed(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.UPD_CANCELLED)


@router.message(StateFilter(UpdatePostForm), CommandStart())
async def update_start_over(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User | None
) -> None:
    await state.clear()
    await send_start_screen(message, session, db_user)


async def _show_preview(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    # Показываем ровно то, что получат люди, — вместе с припиской про раздел.
    entry = update_service.build_broadcast(update_service.build_entry(data["text"]))
    await message.answer(texts.UPD_PREVIEW)
    if data.get("file_id"):
        send = (
            message.answer_photo
            if data.get("file_type") == "photo"
            else message.answer_document
        )
        await send(data["file_id"], caption=entry[:1024])
    else:
        await message.answer(entry)
    await state.set_state(UpdatePostForm.confirm)
    await message.answer(
        texts.UPD_CONFIRM,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=texts.BTN.UPD_SEND,
                        callback_data=UpdatePostCB(action="send").pack(),
                    ),
                    InlineKeyboardButton(
                        text=texts.BTN.CONTENT_CANCEL,
                        callback_data=UpdatePostCB(action="cancel").pack(),
                    ),
                ]
            ]
        ),
    )


@router.message(UpdatePostForm.waiting, F.photo)
async def update_photo(message: Message, state: FSMContext) -> None:
    await state.update_data(
        text=content_service.formatted_text(message) or texts.UPD_EMPTY_TEXT,
        file_id=message.photo[-1].file_id,
        file_type="photo",
    )
    await _show_preview(message, state)


@router.message(UpdatePostForm.waiting, F.document)
async def update_document(message: Message, state: FSMContext) -> None:
    await state.update_data(
        text=content_service.formatted_text(message) or texts.UPD_EMPTY_TEXT,
        file_id=message.document.file_id,
        file_type="document",
    )
    await _show_preview(message, state)


@router.message(UpdatePostForm.waiting, F.text, ~F.text.startswith("/"))
async def update_text(message: Message, state: FSMContext) -> None:
    await state.update_data(
        text=content_service.formatted_text(message), file_id=None, file_type=None
    )
    await _show_preview(message, state)


@router.callback_query(UpdatePostCB.filter())
async def cb_update_action(
    callback: CallbackQuery,
    callback_data: UpdatePostCB,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    if callback_data.action == "cancel":
        await state.clear()
        await callback.message.edit_text(texts.UPD_CANCELLED)
        await callback.answer()
        return
    if await state.get_state() != UpdatePostForm.confirm.state:
        await callback.answer()
        return
    data = await state.get_data()
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    delivered, total = await update_service.publish_update(
        session,
        callback.bot,
        db_user,
        data["text"],
        data.get("file_id"),
        data.get("file_type"),
    )
    await callback.message.answer(texts.UPD_DONE.format(delivered=delivered, total=total))
