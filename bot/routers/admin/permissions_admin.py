"""Панель /admins — управление правами (только для полных админов).

Группа прав = именованный набор модулей. Модуль включается группе или
лично человеку одной кнопкой (✅/⬜). Человек получает права группы,
в которой состоит, плюс личные модули. Все изменения пишутся в аудит.
"""

from html import escape

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.db.models import User
from bot.db.repositories import permission_repo, user_repo
from bot.enums import role_rank
from bot.filters.role_filter import IsAdmin
from bot.keyboards.callback_data import (
    GroupDeleteCB,
    GroupMembersCB,
    GroupOpenCB,
    GroupToggleCB,
    PermCancelCB,
    PermHomeCB,
    PermNewGroupCB,
    PermPersonCB,
    UserGroupSetCB,
    UserModToggleCB,
)
from bot.keyboards.perm_kb import (
    perm_back_to_group_kb,
    perm_cancel_kb,
    perm_group_delete_kb,
    perm_group_kb,
    perm_home_kb,
    perm_person_kb,
)
from bot.services import permission_service
from bot.states.perm_states import PermAdminForm

router = Router(name="admin_permissions")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


async def _home_view(session: AsyncSession):
    groups = await permission_repo.list_all(session)
    text = texts.PERM_HOME + (texts.PERM_HOME_EMPTY if not groups else "")
    return text, perm_home_kb(groups)


async def _person_view(session: AsyncSession, target: User):
    group_label = texts.PERM_NO_GROUP_LABEL
    if target.permission_group_id is not None:
        group = await permission_repo.get(session, target.permission_group_id)
        if group is not None:
            group_label = group.name
    username = f"@{target.username}" if target.username else texts.USERNAME_MISSING
    role = texts.ROLE_LABELS.get(target.current_role, target.current_role.value)
    text = texts.PERM_PERSON_CARD.format(
        name=escape(target.display_name),
        username=escape(username),
        tg_id=target.tg_id,
        role=role,
        group=escape(group_label),
    )
    if role_rank(target.current_role) > 0:
        text += texts.PERM_PERSON_IS_ADMIN_NOTE
    groups = await permission_repo.list_all(session)
    personal = permission_service.personal_modules(target)
    return text, perm_person_kb(target, personal, groups)


@router.message(
    F.chat.type == ChatType.PRIVATE,
    StateFilter(None),
    F.text == texts.BTN.ADMIN_PANEL_PERMS,
)
async def btn_admins(message: Message, session: AsyncSession, state: FSMContext) -> None:
    """Группы прав: «🛠 Админство» → «⚙️ Права». Раньше — команда /admins."""
    await state.clear()
    text, kb = await _home_view(session)
    await message.answer(text, reply_markup=kb)


@router.callback_query(PermHomeCB.filter())
async def cb_home(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    text, kb = await _home_view(session)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# --- Группы: карточка, тогглы модулей, участники, удаление ---


@router.callback_query(GroupOpenCB.filter())
async def cb_group_open(
    callback: CallbackQuery, callback_data: GroupOpenCB, session: AsyncSession
) -> None:
    group = await permission_repo.get(session, callback_data.group_id)
    if group is None:
        await callback.answer(texts.REVIEW_NOT_FOUND, show_alert=True)
        return
    await callback.message.edit_text(
        texts.PERM_GROUP_CARD.format(name=escape(group.name)), reply_markup=perm_group_kb(group)
    )
    await callback.answer()


@router.callback_query(GroupToggleCB.filter())
async def cb_group_toggle(
    callback: CallbackQuery,
    callback_data: GroupToggleCB,
    session: AsyncSession,
    db_user: User,
) -> None:
    group = await permission_repo.get(session, callback_data.group_id)
    if group is None:
        await callback.answer(texts.REVIEW_NOT_FOUND, show_alert=True)
        return
    await permission_service.toggle_group_module(session, db_user, group, callback_data.module)
    await callback.message.edit_reply_markup(reply_markup=perm_group_kb(group))
    await callback.answer()


@router.callback_query(GroupMembersCB.filter())
async def cb_group_members(
    callback: CallbackQuery, callback_data: GroupMembersCB, session: AsyncSession
) -> None:
    group = await permission_repo.get(session, callback_data.group_id)
    if group is None:
        await callback.answer(texts.REVIEW_NOT_FOUND, show_alert=True)
        return
    members = await user_repo.list_by_permission_group(session, group.group_id)
    if members:
        lines = [
            f"• {escape(m.display_name)} · id <code>{m.tg_id}</code>" for m in members
        ]
        text = texts.PERM_MEMBERS_HEADER.format(name=escape(group.name)) + "\n" + "\n".join(lines)
    else:
        text = texts.PERM_MEMBERS_EMPTY.format(
            name=escape(group.name), person_btn=texts.BTN.PERM_PERSON
        )
    await callback.message.edit_text(text, reply_markup=perm_back_to_group_kb(group.group_id))
    await callback.answer()


@router.callback_query(GroupDeleteCB.filter())
async def cb_group_delete(
    callback: CallbackQuery,
    callback_data: GroupDeleteCB,
    session: AsyncSession,
    db_user: User,
) -> None:
    group = await permission_repo.get(session, callback_data.group_id)
    if group is None:
        await callback.answer(texts.REVIEW_NOT_FOUND, show_alert=True)
        return
    if not callback_data.confirmed:
        await callback.message.edit_text(
            texts.PERM_GROUP_DELETE_CONFIRM.format(name=escape(group.name)),
            reply_markup=perm_group_delete_kb(group.group_id),
        )
        await callback.answer()
        return
    name = group.name
    await permission_service.delete_group(session, db_user, group)
    await callback.message.edit_text(texts.PERM_GROUP_DELETED_MSG.format(name=escape(name)))
    text, kb = await _home_view(session)
    await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


# --- Создание группы ---


@router.callback_query(PermNewGroupCB.filter())
async def cb_new_group(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PermAdminForm.group_name)
    await callback.message.answer(texts.PERM_GROUP_CREATE_PROMPT, reply_markup=perm_cancel_kb())
    await callback.answer()


@router.message(PermAdminForm.group_name, F.text, ~F.text.startswith("/"))
async def msg_group_name(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    name = message.text.strip()
    if not (3 <= len(name) <= 100) or "\n" in name:
        await message.answer(texts.PERM_GROUP_NAME_INVALID, reply_markup=perm_cancel_kb())
        return
    if await permission_repo.find_by_name(session, name) is not None:
        await message.answer(texts.PERM_GROUP_NAME_TAKEN, reply_markup=perm_cancel_kb())
        return
    group = await permission_service.create_group(session, db_user, name)
    await state.clear()
    await message.answer(
        texts.PERM_GROUP_CARD.format(name=escape(group.name)), reply_markup=perm_group_kb(group)
    )


# --- Права конкретного человека ---


@router.callback_query(PermPersonCB.filter())
async def cb_person(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PermAdminForm.person_lookup)
    await callback.message.answer(texts.PERM_PERSON_PROMPT, reply_markup=perm_cancel_kb())
    await callback.answer()


@router.message(PermAdminForm.person_lookup, F.text, ~F.text.startswith("/"))
async def msg_person_lookup(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    ref = message.text.strip()
    if ref.lstrip("-").isdigit():
        target = await user_repo.get_by_tg_id(session, int(ref))
    else:
        target = await user_repo.get_by_username(session, ref)
    if target is None:
        await message.answer(texts.USER_NOT_FOUND, reply_markup=perm_cancel_kb())
        return
    await state.clear()
    text, kb = await _person_view(session, target)
    await message.answer(text, reply_markup=kb)


@router.callback_query(UserModToggleCB.filter())
async def cb_user_module(
    callback: CallbackQuery,
    callback_data: UserModToggleCB,
    session: AsyncSession,
    db_user: User,
) -> None:
    target = await user_repo.get_by_tg_id(session, callback_data.tg_id)
    if target is None:
        await callback.answer(texts.USER_NOT_FOUND, show_alert=True)
        return
    await permission_service.toggle_user_module(session, db_user, target, callback_data.module)
    text, kb = await _person_view(session, target)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(UserGroupSetCB.filter())
async def cb_user_group(
    callback: CallbackQuery,
    callback_data: UserGroupSetCB,
    session: AsyncSession,
    db_user: User,
) -> None:
    target = await user_repo.get_by_tg_id(session, callback_data.tg_id)
    if target is None:
        await callback.answer(texts.USER_NOT_FOUND, show_alert=True)
        return
    group = None
    if callback_data.group_id:
        group = await permission_repo.get(session, callback_data.group_id)
        if group is None:
            await callback.answer(texts.REVIEW_NOT_FOUND, show_alert=True)
            return
    await permission_service.set_user_group(session, db_user, target, group)
    text, kb = await _person_view(session, target)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# --- Отмена ввода ---


@router.callback_query(PermCancelCB.filter())
async def cb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(texts.PERM_CANCELLED)
    await callback.answer()
