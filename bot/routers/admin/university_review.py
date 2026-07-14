"""Админ-обработка заявок на вуз и предложений вариантов поиска.

Кнопки на карточках: Принять / Отклонить / Исправить. «Исправить» просит
прислать поправленные данные одним сообщением и обновляет карточку —
так админ убирает опечатки до того, как данные попадут в справочник.
"""

import uuid

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import limits, texts
from bot.db.models import User
from bot.db.repositories import alias_suggestion_repo, university_repo, university_request_repo
from bot.enums import PermissionModule, RequestStatus
from bot.filters.role_filter import HasPerm
from bot.keyboards.admin_kb import (
    alias_suggestion_review_kb,
    review_edit_cancel_kb,
    university_request_review_kb,
)
from bot.keyboards.callback_data import AliasSugCB, ReviewEditCB, UniReqCB
from bot.services import university_service
from bot.states.university_review_states import ReviewEditForm

router = Router(name="admin_university_review")


async def _apply_review_result(callback: CallbackQuery, ok: bool, note: str) -> None:
    if not ok:
        await callback.answer(note, show_alert=True)
        return
    await callback.message.edit_text(
        callback.message.html_text + f"\n\n{note}", reply_markup=None
    )
    await callback.answer(texts.REVIEW_DONE)


def _parse_request_edit(text: str) -> tuple[str, list[str]] | None:
    """Первая строка — название, каждая следующая — вариант поиска."""
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        return None
    name, aliases = lines[0], lines[1:]
    if not (5 <= len(name) <= 255) or len(aliases) > limits.NEW_UNI_ALIASES_MAX:
        return None
    if any(not (limits.ALIAS_MIN <= len(a) <= limits.ALIAS_MAX) for a in aliases):
        return None
    return name, aliases


# --- Заявки на добавление вуза ---


@router.callback_query(UniReqCB.filter(F.action == "approve"), HasPerm(PermissionModule.UNIVERSITIES))
async def cb_uni_approve(
    callback: CallbackQuery, callback_data: UniReqCB, session: AsyncSession, db_user: User
) -> None:
    ok, note = await university_service.approve_request(
        session, callback.bot, uuid.UUID(callback_data.request_id), db_user
    )
    await _apply_review_result(callback, ok, note)


@router.callback_query(UniReqCB.filter(F.action == "reject"), HasPerm(PermissionModule.UNIVERSITIES))
async def cb_uni_reject(
    callback: CallbackQuery, callback_data: UniReqCB, session: AsyncSession, db_user: User
) -> None:
    ok, note = await university_service.reject_request(
        session, callback.bot, uuid.UUID(callback_data.request_id), db_user
    )
    await _apply_review_result(callback, ok, note)


@router.callback_query(UniReqCB.filter(F.action == "edit"), HasPerm(PermissionModule.UNIVERSITIES))
async def cb_uni_edit(
    callback: CallbackQuery, callback_data: UniReqCB, session: AsyncSession, state: FSMContext
) -> None:
    request = await university_request_repo.get(session, uuid.UUID(callback_data.request_id))
    if request is None:
        await callback.answer(texts.REVIEW_NOT_FOUND, show_alert=True)
        return
    if request.status != RequestStatus.PENDING:
        await callback.answer(texts.REVIEW_ALREADY_PROCESSED, show_alert=True)
        return
    await state.set_state(ReviewEditForm.university_request)
    await state.update_data(
        request_id=callback_data.request_id,
        card_chat_id=callback.message.chat.id,
        card_message_id=callback.message.message_id,
    )
    await callback.message.reply(
        texts.UNI_REQ_EDIT_PROMPT.format(limit=limits.NEW_UNI_ALIASES_MAX),
        reply_markup=review_edit_cancel_kb(),
    )
    await callback.answer()


@router.message(ReviewEditForm.university_request, F.text, HasPerm(PermissionModule.UNIVERSITIES))
async def msg_uni_edit(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    parsed = _parse_request_edit(message.text)
    if parsed is None:
        await message.answer(
            texts.UNI_REQ_EDIT_INVALID.format(
                limit=limits.NEW_UNI_ALIASES_MAX, min=limits.ALIAS_MIN, max=limits.ALIAS_MAX
            ),
            reply_markup=review_edit_cancel_kb(),
        )
        return
    name, aliases = parsed
    data = await state.get_data()
    request_id = uuid.UUID(data["request_id"])
    ok, note = await university_service.edit_request_data(
        session, request_id, name, aliases, db_user
    )
    await state.clear()
    if not ok:
        await message.answer(note)
        return
    request = await university_request_repo.get(session, request_id)
    card = university_service.render_request_card(request)
    card += texts.UNI_REQ_EDITED_MARK.format(admin=db_user.display_name)
    await message.bot.edit_message_text(
        card,
        chat_id=data["card_chat_id"],
        message_id=data["card_message_id"],
        reply_markup=university_request_review_kb(request_id),
    )
    await message.answer(texts.EDIT_SAVED)


# --- Предложения вариантов поиска ---


@router.callback_query(AliasSugCB.filter(F.action == "approve"), HasPerm(PermissionModule.UNIVERSITIES))
async def cb_alias_approve(
    callback: CallbackQuery, callback_data: AliasSugCB, session: AsyncSession, db_user: User
) -> None:
    ok, note = await university_service.approve_alias(
        session, callback.bot, uuid.UUID(callback_data.suggestion_id), db_user
    )
    await _apply_review_result(callback, ok, note)


@router.callback_query(AliasSugCB.filter(F.action == "reject"), HasPerm(PermissionModule.UNIVERSITIES))
async def cb_alias_reject(
    callback: CallbackQuery, callback_data: AliasSugCB, session: AsyncSession, db_user: User
) -> None:
    ok, note = await university_service.reject_alias(
        session, callback.bot, uuid.UUID(callback_data.suggestion_id), db_user
    )
    await _apply_review_result(callback, ok, note)


@router.callback_query(AliasSugCB.filter(F.action == "edit"), HasPerm(PermissionModule.UNIVERSITIES))
async def cb_alias_edit(
    callback: CallbackQuery, callback_data: AliasSugCB, session: AsyncSession, state: FSMContext
) -> None:
    suggestion = await alias_suggestion_repo.get(
        session, uuid.UUID(callback_data.suggestion_id)
    )
    if suggestion is None:
        await callback.answer(texts.REVIEW_NOT_FOUND, show_alert=True)
        return
    if suggestion.status != RequestStatus.PENDING:
        await callback.answer(texts.REVIEW_ALREADY_PROCESSED, show_alert=True)
        return
    await state.set_state(ReviewEditForm.alias_suggestion)
    await state.update_data(
        suggestion_id=callback_data.suggestion_id,
        card_chat_id=callback.message.chat.id,
        card_message_id=callback.message.message_id,
    )
    await callback.message.reply(
        texts.ALIAS_EDIT_PROMPT, reply_markup=review_edit_cancel_kb()
    )
    await callback.answer()


@router.message(ReviewEditForm.alias_suggestion, F.text, HasPerm(PermissionModule.UNIVERSITIES))
async def msg_alias_edit(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    alias = message.text.strip()
    if not (limits.ALIAS_MIN <= len(alias) <= limits.ALIAS_MAX) or "\n" in alias:
        await message.answer(
            texts.ALIAS_EDIT_INVALID.format(min=limits.ALIAS_MIN, max=limits.ALIAS_MAX),
            reply_markup=review_edit_cancel_kb(),
        )
        return
    data = await state.get_data()
    suggestion_id = uuid.UUID(data["suggestion_id"])
    ok, note = await university_service.edit_alias_text(session, suggestion_id, alias, db_user)
    await state.clear()
    if not ok:
        await message.answer(note)
        return
    suggestion = await alias_suggestion_repo.get(session, suggestion_id)
    university = await university_repo.get(session, suggestion.university_id)
    card = university_service.render_alias_card(
        suggestion, university.canonical_name if university else "?"
    )
    card += texts.UNI_REQ_EDITED_MARK.format(admin=db_user.display_name)
    await message.bot.edit_message_text(
        card,
        chat_id=data["card_chat_id"],
        message_id=data["card_message_id"],
        reply_markup=alias_suggestion_review_kb(suggestion_id),
    )
    await message.answer(texts.EDIT_SAVED)


# --- Отмена исправления ---


@router.callback_query(ReviewEditCB.filter(F.action == "cancel"), HasPerm(PermissionModule.UNIVERSITIES))
async def cb_edit_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(texts.EDIT_CANCELLED)
    await callback.answer()


# --- Кнопки нажал не админ ---


@router.callback_query(UniReqCB.filter())
async def cb_uni_not_admin(callback: CallbackQuery) -> None:
    await callback.answer(texts.REVIEW_ADMIN_ONLY, show_alert=True)


@router.callback_query(AliasSugCB.filter())
async def cb_alias_not_admin(callback: CallbackQuery) -> None:
    await callback.answer(texts.REVIEW_ADMIN_ONLY, show_alert=True)
