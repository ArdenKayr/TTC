import uuid

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.db.models import User
from bot.enums import PermissionModule
from bot.filters.role_filter import HasPerm
from bot.keyboards.callback_data import RegReviewCB
from bot.routers.admin import review_ui
from bot.services import registration_service

router = Router(name="admin_registration_review")


@router.callback_query(RegReviewCB.filter(F.action == "approve"), HasPerm(PermissionModule.REGISTRATION))
async def cb_approve(
    callback: CallbackQuery,
    callback_data: RegReviewCB,
    session: AsyncSession,
    db_user: User,
) -> None:
    await review_ui.ack(callback)
    ok, note = await registration_service.approve(
        session, callback.bot, uuid.UUID(callback_data.request_id), db_user
    )
    await review_ui.show_result(callback, ok, note)


@router.callback_query(RegReviewCB.filter(F.action == "reject"), HasPerm(PermissionModule.REGISTRATION))
async def cb_reject(
    callback: CallbackQuery,
    callback_data: RegReviewCB,
    session: AsyncSession,
    db_user: User,
) -> None:
    await review_ui.ack(callback)
    ok, note = await registration_service.reject(
        session, callback.bot, uuid.UUID(callback_data.request_id), db_user
    )
    await review_ui.show_result(callback, ok, note)


@router.callback_query(RegReviewCB.filter())
async def cb_not_admin(callback: CallbackQuery) -> None:
    await callback.answer(texts.REVIEW_ADMIN_ONLY, show_alert=True)
