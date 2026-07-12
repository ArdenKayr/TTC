import uuid

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.db.models import User
from bot.filters.role_filter import IsAdmin
from bot.keyboards.callback_data import RegReviewCB
from bot.services import registration_service

router = Router(name="admin_registration_review")


async def _apply_review_result(callback: CallbackQuery, ok: bool, note: str) -> None:
    if not ok:
        await callback.answer(note, show_alert=True)
        return
    await callback.message.edit_text(
        callback.message.html_text + f"\n\n{note}", reply_markup=None
    )
    await callback.answer(texts.REVIEW_DONE)


@router.callback_query(RegReviewCB.filter(F.action == "approve"), IsAdmin())
async def cb_approve(
    callback: CallbackQuery,
    callback_data: RegReviewCB,
    session: AsyncSession,
    db_user: User,
) -> None:
    ok, note = await registration_service.approve(
        session, callback.bot, uuid.UUID(callback_data.request_id), db_user
    )
    await _apply_review_result(callback, ok, note)


@router.callback_query(RegReviewCB.filter(F.action == "reject"), IsAdmin())
async def cb_reject(
    callback: CallbackQuery,
    callback_data: RegReviewCB,
    session: AsyncSession,
    db_user: User,
) -> None:
    ok, note = await registration_service.reject(
        session, callback.bot, uuid.UUID(callback_data.request_id), db_user
    )
    await _apply_review_result(callback, ok, note)


@router.callback_query(RegReviewCB.filter())
async def cb_not_admin(callback: CallbackQuery) -> None:
    await callback.answer(texts.REVIEW_ADMIN_ONLY, show_alert=True)
