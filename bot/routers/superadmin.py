"""Панель суперадмина: «Манипуляция с пользователем».

Ввод tg_id/@username → карточка с действиями: кастомить права (открывает
карточку прав из /admins), сделать админом, снять админство, забанить.
Иерархия (кого можно трогать) проверяется в role_service.
"""

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
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.db.models import User
from bot.db.repositories import user_repo
from bot.enums import UserRole
from bot.filters.role_filter import IsSuperadmin
from bot.keyboards.activity_kb import form_cancel_kb
from bot.keyboards.callback_data import SuperUserCB
from bot.keyboards.common_kb import admin_panel_kb
from bot.routers.admin.permissions_admin import _person_view
from bot.routers.common import send_start_screen
from bot.services import role_service
from bot.states.superadmin_states import SuperadminForm

router = Router(name="superadmin")
router.message.filter(IsSuperadmin())
router.callback_query.filter(IsSuperadmin())

_PRIVATE = F.chat.type == ChatType.PRIVATE


def _user_card(target: User) -> tuple[str, InlineKeyboardMarkup]:
    username = f"@{target.username}" if target.username else texts.PROFILE_EMPTY_FIELD
    text = texts.SUPER_USER_CARD.format(
        name=escape(target.display_name),
        username=escape(username),
        tg_id=target.tg_id,
        role=texts.ROLE_LABELS.get(target.current_role, target.current_role.value),
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BTN.SUPER_CUSTOM,
                    callback_data=SuperUserCB(action="custom", tg_id=target.tg_id).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=texts.BTN.SUPER_MAKE_ADMIN,
                    callback_data=SuperUserCB(action="make_admin", tg_id=target.tg_id).pack(),
                ),
                InlineKeyboardButton(
                    text=texts.BTN.SUPER_REMOVE_ADMIN,
                    callback_data=SuperUserCB(action="remove_admin", tg_id=target.tg_id).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=texts.BTN.SUPER_BAN,
                    callback_data=SuperUserCB(action="ban", tg_id=target.tg_id).pack(),
                )
            ],
        ]
    )
    return text, kb


@router.message(_PRIVATE, StateFilter(None), F.text == texts.BTN.ADMIN_PANEL_USERS)
async def start_user_lookup(message: Message, state: FSMContext) -> None:
    await state.set_state(SuperadminForm.user_ref)
    await message.answer(texts.SUPER_USER_PROMPT, reply_markup=form_cancel_kb())


@router.message(StateFilter(SuperadminForm), F.text == texts.BTN.REG_CANCEL)
async def lookup_cancel(message: Message, state: FSMContext, db_user: User) -> None:
    await state.clear()
    await message.answer(
        texts.ADMIN_MODE_ON,
        reply_markup=admin_panel_kb(db_user.current_role == UserRole.OWNER),
    )


@router.message(StateFilter(SuperadminForm), CommandStart())
async def lookup_start_over(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User | None
) -> None:
    await state.clear()
    await send_start_screen(message, session, db_user)


@router.message(SuperadminForm.user_ref, F.text, ~F.text.startswith("/"))
async def lookup_user(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    ref = message.text.strip()
    if ref.lstrip("-").isdigit():
        target = await user_repo.get_by_tg_id(session, int(ref))
    else:
        target = await user_repo.get_by_username(session, ref)
    if target is None:
        await message.answer(texts.USER_NOT_FOUND)
        return
    await state.clear()
    await message.answer(
        texts.ADMIN_MODE_ON,
        reply_markup=admin_panel_kb(db_user.current_role == UserRole.OWNER),
    )
    text, kb = _user_card(target)
    await message.answer(text, reply_markup=kb)


async def _refresh_card(callback: CallbackQuery, target: User) -> None:
    text, kb = _user_card(target)
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:  # текст не изменился — Telegram не даёт править без изменений
        pass


@router.callback_query(SuperUserCB.filter())
async def cb_user_action(
    callback: CallbackQuery,
    callback_data: SuperUserCB,
    session: AsyncSession,
    db_user: User,
) -> None:
    target = await user_repo.get_by_tg_id(session, callback_data.tg_id)
    if target is None:
        await callback.answer(texts.USER_NOT_FOUND, show_alert=True)
        return

    if callback_data.action == "custom":
        text, kb = await _person_view(session, target)
        await callback.message.answer(text, reply_markup=kb)
        await callback.answer()
        return

    if callback_data.action == "make_admin":
        error = await role_service.set_role(session, db_user, target, UserRole.ADMIN)
    elif callback_data.action == "remove_admin":
        if target.current_role != UserRole.ADMIN:
            await callback.answer(texts.SUPER_NOT_ADMIN, show_alert=True)
            return
        error = await role_service.set_role(session, db_user, target, UserRole.USER)
    elif callback_data.action == "ban":
        error = await role_service.ban_user(session, callback.bot, db_user, target, None)
    else:
        await callback.answer()
        return

    if error:
        await callback.answer(error, show_alert=True)
        return
    await _refresh_card(callback, target)
    await callback.answer(texts.SUPER_DONE)
