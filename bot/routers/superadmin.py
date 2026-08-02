"""Раздел «👤 Пользователи»: карточка человека и всё, что с ним можно сделать.

Ввод tg_id/@username → карточка: права, роли, бан и разбан. Что именно видно
в карточке, зависит от того, кто смотрит: роли раздаёт только суперадмин,
права правит только полный админ, а бан и разбан доступны всем, у кого есть
модуль «Бан и разбан». Иерархия (кого вообще можно трогать) проверяется
в role_service.

Раздел закрыт модулем «Бан и разбан», а не ролью: полные админы проходят по
модулю автоматически, а «модульному» админу это единственный способ забанить —
команд /ban и /unban больше нет.
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
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot import limits, texts
from bot.db.models import User
from bot.db.repositories import user_repo
from bot.enums import FULL_ADMIN_ROLES, PermissionModule, UserRole
from bot.filters.role_filter import HasPerm
from bot.keyboards.activity_kb import form_cancel_kb
from bot.keyboards.callback_data import SuperUserCB
from bot.keyboards.common_kb import MENU_BUTTON_TEXTS, admin_panel_kb
from bot.routers.admin.permissions_admin import _person_view
from bot.routers.common import send_start_screen
from bot.services import permission_service, role_service, scenario_service
from bot.states.superadmin_states import SuperadminForm

router = Router(name="superadmin")
router.message.filter(HasPerm(PermissionModule.MODERATION))
router.callback_query.filter(HasPerm(PermissionModule.MODERATION))

_PRIVATE = F.chat.type == ChatType.PRIVATE


async def _panel(session, db_user: User) -> ReplyKeyboardMarkup:
    """Нижнее меню админской панели под права этого человека."""
    modules = await permission_service.effective_modules(session, db_user)
    return admin_panel_kb(db_user, modules)


def _ban_reason_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=texts.BTN.BAN_NO_REASON),
                KeyboardButton(text=texts.BTN.REG_CANCEL),
            ]
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def _user_card(target: User, actor: User) -> tuple[str, InlineKeyboardMarkup]:
    username = f"@{target.username}" if target.username else texts.PROFILE_EMPTY_FIELD
    text = texts.SUPER_USER_CARD.format(
        name=escape(target.display_name),
        username=escape(username),
        tg_id=target.tg_id,
        role=texts.ROLE_LABELS.get(target.current_role, target.current_role.value),
    )

    def button(label: str, action: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(
            text=label,
            callback_data=SuperUserCB(action=action, tg_id=target.tg_id).pack(),
        )

    # Что показывать — решают права смотрящего, а не роль подопечного:
    # роли раздаёт суперадмин, права правит полный админ, банить может любой
    # с модулем «Бан и разбан».
    roles = role_service.assignable_roles(actor)
    rows: list[list[InlineKeyboardButton]] = []
    if actor.current_role in FULL_ADMIN_ROLES:
        rows.append([button(texts.BTN.SUPER_CUSTOM, "custom")])
    if UserRole.ADMIN in roles:
        rows.append(
            [
                button(texts.BTN.SUPER_MAKE_ADMIN, "make_admin"),
                button(texts.BTN.SUPER_REMOVE_ADMIN, "remove_admin"),
            ]
        )
    # Суперадминов назначает и снимает только владелец.
    if UserRole.SUPERADMIN in roles:
        rows.append(
            [
                button(texts.BTN.SUPER_MAKE_SUPER, "make_super"),
                button(texts.BTN.SUPER_REMOVE_SUPER, "remove_super"),
            ]
        )
    # Роли без админского смысла: раньше выдавались только командой /setrole.
    plain = [
        (UserRole.ORGANIZER, texts.BTN.SUPER_ROLE_ORG, "role_organizer"),
        (UserRole.USER, texts.BTN.SUPER_ROLE_USER, "role_user"),
        (UserRole.CUSTOM, texts.BTN.SUPER_ROLE_CUSTOM, "role_custom"),
    ]
    plain_row = [button(label, action) for role, label, action in plain if role in roles]
    if plain_row:
        rows.append(plain_row)
    # Забанен — предлагаем снять бан, а не забанить ещё раз.
    if target.current_role == UserRole.BANNED:
        rows.append([button(texts.BTN.SUPER_UNBAN, "unban")])
    else:
        rows.append([button(texts.BTN.SUPER_BAN, "ban")])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(_PRIVATE, StateFilter(None), F.text == texts.BTN.ADMIN_PANEL_USERS)
async def start_user_lookup(message: Message, state: FSMContext) -> None:
    await state.set_state(SuperadminForm.user_ref)
    await message.answer(texts.SUPER_USER_PROMPT, reply_markup=form_cancel_kb())


@router.message(StateFilter(SuperadminForm), F.text == texts.BTN.REG_CANCEL)
async def lookup_cancel(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    await state.clear()
    await message.answer(texts.ADMIN_MODE_ON, reply_markup=await _panel(session, db_user))


@router.message(StateFilter(SuperadminForm), F.text.in_(MENU_BUTTON_TEXTS))
async def form_menu_pressed(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    """Кнопка меню посреди ввода — это выход, а не значение.

    Иначе нажатие «📄 Разделы» на шаге причины бана записалось бы в журнал
    как причина.
    """
    await state.clear()
    await message.answer(texts.ADMIN_MODE_ON, reply_markup=await _panel(session, db_user))


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
    await message.answer(texts.ADMIN_MODE_ON, reply_markup=await _panel(session, db_user))
    text, kb = _user_card(target, db_user)
    await message.answer(text, reply_markup=kb)


async def _refresh_card(callback: CallbackQuery, target: User, actor: User) -> None:
    text, kb = _user_card(target, actor)
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:  # текст не изменился — Telegram не даёт править без изменений
        pass


# Кнопка -> роль, которую она выдаёт. Раньше всё, кроме админства, можно было
# назначить только командой /setrole.
_ROLE_ACTIONS = {
    "make_admin": UserRole.ADMIN,
    "make_super": UserRole.SUPERADMIN,
    "role_organizer": UserRole.ORGANIZER,
    "role_user": UserRole.USER,
    "role_custom": UserRole.CUSTOM,
}


@router.callback_query(SuperUserCB.filter())
async def cb_user_action(
    callback: CallbackQuery,
    callback_data: SuperUserCB,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    target = await user_repo.get_by_tg_id(session, callback_data.tg_id)
    if target is None:
        await callback.answer(texts.USER_NOT_FOUND, show_alert=True)
        return
    action = callback_data.action

    if action == "custom":
        if db_user.current_role not in FULL_ADMIN_ROLES:
            await callback.answer(texts.ROLE_NO_RIGHTS, show_alert=True)
            return
        text, kb = await _person_view(session, target)
        await callback.message.answer(text, reply_markup=kb)
        await callback.answer()
        return

    if action == "ban":
        # Причина спрашивается отдельным шагом: кнопка банила молча, записать
        # причину можно было только командой /ban — теперь наоборот.
        if target.tg_id == db_user.tg_id:
            await callback.answer(texts.BAN_SELF, show_alert=True)
            return
        await state.set_state(SuperadminForm.ban_reason)
        await state.update_data(target=target.tg_id)
        await callback.message.answer(
            texts.BAN_REASON_PROMPT.format(
                name=escape(target.display_name), skip=texts.BTN.BAN_NO_REASON
            ),
            reply_markup=_ban_reason_kb(),
        )
        await callback.answer()
        return

    bot = callback.bot
    notified = True
    if action == "unban":
        error = await role_service.unban_user(session, bot, db_user, target)
    elif action == "remove_admin":
        if target.current_role != UserRole.ADMIN:
            await callback.answer(texts.SUPER_NOT_ADMIN, show_alert=True)
            return
        error, notified = await role_service.set_role(
            session, bot, db_user, target, UserRole.USER
        )
    elif action == "remove_super":
        if target.current_role != UserRole.SUPERADMIN:
            await callback.answer(texts.SUPER_NOT_SUPER, show_alert=True)
            return
        error, notified = await role_service.set_role(
            session, bot, db_user, target, UserRole.ADMIN
        )
    elif action in _ROLE_ACTIONS:
        error, notified = await role_service.set_role(
            session, bot, db_user, target, _ROLE_ACTIONS[action]
        )
    else:
        await callback.answer()
        return

    if error:
        await callback.answer(error, show_alert=True)
        return
    await _refresh_card(callback, target, db_user)
    # Роль сменилась, но человек об этом не узнал — говорим об этом сразу
    # модальным окном, а не тихим тостом, который легко пропустить.
    if notified:
        await callback.answer(texts.SUPER_DONE)
    else:
        await callback.answer(texts.SUPER_DONE + texts.SETROLE_DM_FAILED, show_alert=True)


@router.message(SuperadminForm.ban_reason, F.text, ~F.text.startswith("/"))
async def ban_with_reason(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    data = await state.get_data()
    target = await user_repo.get_by_tg_id(session, data.get("target", 0))
    if target is None:
        await state.clear()
        await message.answer(texts.USER_NOT_FOUND, reply_markup=await _panel(session, db_user))
        return

    raw = message.text.strip()
    if raw == texts.BTN.BAN_NO_REASON:
        reason = None
    elif len(raw) > limits.BAN_REASON_MAX:
        await message.answer(
            texts.BAN_REASON_TOO_LONG.format(
                max=limits.BAN_REASON_MAX, skip=texts.BTN.BAN_NO_REASON
            )
        )
        return
    else:
        reason = raw

    await state.clear()
    error = await role_service.ban_user(session, message.bot, db_user, target, reason)
    panel = await _panel(session, db_user)
    if error:
        await message.answer(error, reply_markup=panel)
        return
    await scenario_service.reply(
        message,
        session,
        "ban_done",
        panel,
        name=target.display_name,
        tg_id=target.tg_id,
    )
    # Карточку показываем заново: теперь в ней «Разбанить» вместо «Забанить».
    text, kb = _user_card(target, db_user)
    await message.answer(text, reply_markup=kb)
