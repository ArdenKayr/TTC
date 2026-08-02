"""Решения по мероприятиям и голосованиям (модуль прав «Мероприятия»).

- Кнопки Принять/Отклонить на карточках заявок в админ-чате.
- «🛠 Админство» → «📅 Мероприятия» — список активных мероприятий с кнопками
  «Завершить»/«Отменить» (пометка в Афише + авто-снятие роли организатора).
"""

import uuid
from datetime import timedelta, timezone
from html import escape

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.db.models import User
from bot.enums import PermissionModule
from bot.filters.role_filter import HasPerm
from bot.keyboards.activity_kb import act_lifecycle_kb
from bot.keyboards.callback_data import ActLifecycleCB, ActReviewCB, VoteReviewCB
from bot.services import activity_service

router = Router(name="admin_activity_review")

_MSK = timezone(timedelta(hours=3))


async def _apply_review_result(callback: CallbackQuery, ok: bool, note: str) -> None:
    if not ok:
        await callback.answer(note, show_alert=True)
        return
    await callback.message.edit_text(
        callback.message.html_text + f"\n\n{note}", reply_markup=None
    )
    await callback.answer(texts.REVIEW_DONE)


@router.callback_query(ActReviewCB.filter(F.action == "approve"), HasPerm(PermissionModule.ACTIVITIES))
async def cb_act_approve(
    callback: CallbackQuery, callback_data: ActReviewCB, session: AsyncSession, db_user: User
) -> None:
    ok, note = await activity_service.approve_activity(
        session, callback.bot, uuid.UUID(callback_data.request_id), db_user
    )
    await _apply_review_result(callback, ok, note)


@router.callback_query(ActReviewCB.filter(F.action == "reject"), HasPerm(PermissionModule.ACTIVITIES))
async def cb_act_reject(
    callback: CallbackQuery, callback_data: ActReviewCB, session: AsyncSession, db_user: User
) -> None:
    ok, note = await activity_service.reject_activity(
        session, callback.bot, uuid.UUID(callback_data.request_id), db_user
    )
    await _apply_review_result(callback, ok, note)


@router.callback_query(VoteReviewCB.filter(F.action == "approve"), HasPerm(PermissionModule.ACTIVITIES))
async def cb_vote_approve(
    callback: CallbackQuery, callback_data: VoteReviewCB, session: AsyncSession, db_user: User
) -> None:
    ok, note = await activity_service.approve_vote(
        session, callback.bot, uuid.UUID(callback_data.request_id), db_user
    )
    await _apply_review_result(callback, ok, note)


@router.callback_query(VoteReviewCB.filter(F.action == "reject"), HasPerm(PermissionModule.ACTIVITIES))
async def cb_vote_reject(
    callback: CallbackQuery, callback_data: VoteReviewCB, session: AsyncSession, db_user: User
) -> None:
    ok, note = await activity_service.reject_vote(
        session, callback.bot, uuid.UUID(callback_data.request_id), db_user
    )
    await _apply_review_result(callback, ok, note)


@router.message(
    F.chat.type == ChatType.PRIVATE,
    StateFilter(None),
    F.text == texts.BTN.ADMIN_PANEL_ACTIVITIES,
    HasPerm(PermissionModule.ACTIVITIES),
)
async def btn_activities(message: Message, session: AsyncSession) -> None:
    """Активные мероприятия с кнопками «Завершить» и «Отменить».

    Раньше открывалось командой /activities — единственным способом закрыть
    прошедшее мероприятие, о котором надо было знать заранее.
    """
    activities = await activity_service.list_active(session)
    if not activities:
        await message.answer(texts.ACT_LIST_EMPTY)
        return
    for activity in activities:
        organizer = (
            await session.get(User, activity.organizer_id) if activity.organizer_id else None
        )
        organizer_label = activity_service.user_label(organizer)
        await message.answer(
            texts.ACT_LIST_ITEM.format(
                title=escape(activity.title),
                organizer=organizer_label,
                date=activity.created_at.astimezone(_MSK).strftime("%d.%m.%Y"),
            ),
            reply_markup=act_lifecycle_kb(str(activity.activity_id)),
        )


@router.callback_query(ActLifecycleCB.filter(), HasPerm(PermissionModule.ACTIVITIES))
async def cb_act_lifecycle(
    callback: CallbackQuery, callback_data: ActLifecycleCB, session: AsyncSession, db_user: User
) -> None:
    ok, note = await activity_service.finish_activity(
        session,
        callback.bot,
        uuid.UUID(callback_data.activity_id),
        db_user,
        cancelled=callback_data.action == "cancel",
    )
    await _apply_review_result(callback, ok, note)


@router.callback_query(ActReviewCB.filter())
@router.callback_query(VoteReviewCB.filter())
@router.callback_query(ActLifecycleCB.filter())
async def cb_no_permission(callback: CallbackQuery) -> None:
    await callback.answer(texts.REVIEW_ADMIN_ONLY, show_alert=True)
