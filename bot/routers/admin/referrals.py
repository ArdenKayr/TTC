"""Ссылки-приглашения («🛠 Админство» → «🔗 Приглашения»).

Раздел без своего модуля прав: это не участок работы, а именной счётчик того,
кто и так отвечает за набор целиком, — поэтому он открыт полным админам.
Разница внутри: админ видит и заводит ссылки только себе, суперадмин и
владелец видят все и выдают их людям поимённо (в том числе тем, у кого
админских прав нет вовсе).

Механика счёта живёт в `bot/services/referral_service.py`, здесь — только
разговор с человеком.
"""

from contextlib import suppress
from html import escape

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot import limits, texts
from bot.db.models import User
from bot.db.repositories import audit_repo, referral_repo, user_repo
from bot.enums import AuditAction
from bot.filters.role_filter import IsAdmin
from bot.keyboards.callback_data import RefDeleteCB, RefNewCB
from bot.keyboards.common_kb import MENU_BUTTON_TEXTS, admin_panel_kb
from bot.keyboards.registration_kb import form_cancel_kb
from bot.routers.common import send_start_screen
from bot.services import input_guard, permission_service, referral_service
from bot.states.referral_states import ReferralForm

router = Router(name="admin_referrals")

_PRIVATE = F.chat.type == ChatType.PRIVATE


async def _panel(session: AsyncSession, db_user: User) -> ReplyKeyboardMarkup:
    modules = await permission_service.effective_modules(session, db_user)
    return admin_panel_kb(db_user, modules)


def _home_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.BTN.REF_NEW, callback_data=RefNewCB().pack())]
        ]
    )


def _card_kb(code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BTN.REF_DELETE,
                    callback_data=RefDeleteCB(code=code).pack(),
                )
            ]
        ]
    )


def _confirm_kb(code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BTN.REF_DELETE_YES,
                    callback_data=RefDeleteCB(code=code, confirmed=True).pack(),
                )
            ]
        ]
    )


def _owner_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=texts.BTN.REF_SELF),
                KeyboardButton(text=texts.BTN.REG_CANCEL),
            ]
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


# --- Список ссылок ---


@router.message(
    _PRIVATE,
    StateFilter(None),
    F.text == texts.BTN.ADMIN_PANEL_REFERRALS,
    IsAdmin(),
)
async def btn_referrals(message: Message, session: AsyncSession, db_user: User) -> None:
    sees_all = referral_service.may_see_all(db_user)
    links = await referral_repo.list_links(
        session, None if sees_all else db_user.tg_id
    )
    await message.answer(texts.REF_HOME, reply_markup=_home_kb())
    if not links:
        await message.answer(texts.REF_EMPTY.format(new=texts.BTN.REF_NEW))
        return
    for link, card in await referral_service.render_links(
        session, message.bot, links, with_owner=sees_all
    ):
        await message.answer(card, reply_markup=_card_kb(link.code))


# --- Создание ---


@router.callback_query(RefNewCB.filter(), IsAdmin())
async def cb_new_link(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ReferralForm.title)
    await callback.message.answer(
        texts.REF_NEW_PROMPT.format(min=limits.REF_TITLE_MIN, max=limits.REF_TITLE_MAX),
        reply_markup=form_cancel_kb(),
    )
    await callback.answer()


@router.message(StateFilter(ReferralForm), F.text == texts.BTN.REG_CANCEL)
async def form_cancel(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    await state.clear()
    await message.answer(texts.REF_CANCELLED, reply_markup=await _panel(session, db_user))


@router.message(StateFilter(ReferralForm), F.text.in_(MENU_BUTTON_TEXTS))
async def form_menu_pressed(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    """Кнопка меню посреди ввода — это выход, а не название ссылки."""
    await state.clear()
    await message.answer(texts.REF_CANCELLED, reply_markup=await _panel(session, db_user))


@router.message(StateFilter(ReferralForm), CommandStart())
async def form_start_over(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User | None
) -> None:
    await state.clear()
    await send_start_screen(message, session, db_user)


async def _create(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    *,
    owner: User,
    actor: User,
    title: str,
) -> None:
    """Заводит ссылку и сразу показывает её карточку — готовую к отправке."""
    if await referral_repo.count_links(session, owner.tg_id) >= limits.REF_LINKS_PER_USER:
        await state.clear()
        await message.answer(
            texts.REF_LIMIT.format(max=limits.REF_LINKS_PER_USER),
            reply_markup=await _panel(session, actor),
        )
        return

    code = await referral_service.unique_code(session)
    link = await referral_repo.create_link(
        session, code=code, owner_tg_id=owner.tg_id, title=title, created_by=actor.tg_id
    )
    await audit_repo.add(
        session,
        AuditAction.REFERRAL_LINK_CREATED,
        actor_tg_id=actor.tg_id,
        target_tg_id=owner.tg_id,
        target_entity_type="referral_link",
        target_entity_id=code,
        meta={"title": title},
    )
    await session.commit()
    await state.clear()

    cards = await referral_service.render_links(
        session, message.bot, [link], with_owner=owner.tg_id != actor.tg_id
    )
    await message.answer(texts.ADMIN_MODE_ON, reply_markup=await _panel(session, actor))
    await message.answer(texts.REF_CREATED + cards[0][1], reply_markup=_card_kb(code))


@router.message(ReferralForm.title, F.text, ~F.text.startswith("/"))
async def form_title(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    title = message.text.strip()
    if not limits.REF_TITLE_MIN <= len(title) <= limits.REF_TITLE_MAX:
        await message.answer(
            texts.REF_TITLE_BAD.format(min=limits.REF_TITLE_MIN, max=limits.REF_TITLE_MAX)
        )
        return
    # Обычный админ заводит ссылку только себе — спрашивать его «кому» незачем.
    if not referral_service.may_see_all(db_user):
        await _create(message, session, state, owner=db_user, actor=db_user, title=title)
        return
    await state.update_data(title=title)
    await state.set_state(ReferralForm.owner)
    await message.answer(
        texts.REF_OWNER_PROMPT.format(self=texts.BTN.REF_SELF), reply_markup=_owner_kb()
    )


@router.message(ReferralForm.owner, F.text == texts.BTN.REF_SELF)
async def form_owner_self(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    data = await state.get_data()
    await _create(message, session, state, owner=db_user, actor=db_user, title=data["title"])


@router.message(ReferralForm.owner, F.text, ~F.text.startswith("/"))
async def form_owner(
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
    data = await state.get_data()
    await _create(message, session, state, owner=target, actor=db_user, title=data["title"])


@router.message(StateFilter(ReferralForm))
async def form_unexpected(message: Message, state: FSMContext) -> None:
    """Шаг ждёт текст, а пришло фото или стикер — молчать в ответ нельзя."""
    await message.answer(input_guard.form_explain(message))
    if await state.get_state() == ReferralForm.owner.state:
        await message.answer(
            texts.REF_OWNER_PROMPT.format(self=texts.BTN.REF_SELF), reply_markup=_owner_kb()
        )
        return
    await message.answer(
        texts.REF_NEW_PROMPT.format(min=limits.REF_TITLE_MIN, max=limits.REF_TITLE_MAX),
        reply_markup=form_cancel_kb(),
    )


# --- Удаление ---


@router.callback_query(RefDeleteCB.filter(), IsAdmin())
async def cb_delete(
    callback: CallbackQuery,
    callback_data: RefDeleteCB,
    session: AsyncSession,
    db_user: User,
) -> None:
    link = await referral_repo.get_link(session, callback_data.code)
    if link is None:
        await callback.answer(texts.REF_GONE, show_alert=True)
        return
    if not referral_service.may_delete(db_user, link):
        await callback.answer(texts.REF_NOT_YOURS, show_alert=True)
        return

    if not callback_data.confirmed:
        await callback.message.answer(
            texts.REF_DELETE_CONFIRM.format(title=escape(link.title)),
            reply_markup=_confirm_kb(link.code),
        )
        await callback.answer()
        return

    title = link.title
    await referral_repo.delete_link(session, link)
    await audit_repo.add(
        session,
        AuditAction.REFERRAL_LINK_DELETED,
        actor_tg_id=db_user.tg_id,
        target_tg_id=link.owner_tg_id,
        target_entity_type="referral_link",
        target_entity_id=callback_data.code,
        meta={"title": title},
    )
    await session.commit()
    # Кнопка под подтверждением больше ничего не значит: ссылки нет. Убираем,
    # чтобы на неё не жали второй раз и не получали «этой ссылки уже нет».
    with suppress(TelegramAPIError):
        await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(texts.REF_DELETED.format(title=escape(title)))
    await callback.answer()


@router.callback_query(RefNewCB.filter())
@router.callback_query(RefDeleteCB.filter())
async def cb_no_permission(callback: CallbackQuery) -> None:
    await callback.answer(texts.REVIEW_ADMIN_ONLY, show_alert=True)
