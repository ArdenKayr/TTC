"""«Мой профиль»: карточка, изменение полей, удаление аккаунта."""

from datetime import date, datetime

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

from bot import limits, texts
from bot.db.models import User
from bot.keyboards.activity_kb import form_cancel_kb
from bot.keyboards.callback_data import ProfileDeleteCB, ProfileEditCB
from bot.keyboards.common_kb import main_menu_kb
from bot.routers.common import send_start_screen
from bot.services import profile_service
from bot.states.profile_states import ProfileForm

router = Router(name="profile")


def profile_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BTN.PROFILE_EDIT_NICK,
                    callback_data=ProfileEditCB(field="nick").pack(),
                ),
                InlineKeyboardButton(
                    text=texts.BTN.PROFILE_EDIT_GROUP,
                    callback_data=ProfileEditCB(field="group").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=texts.BTN.PROFILE_EDIT_BIRTH,
                    callback_data=ProfileEditCB(field="birth").pack(),
                ),
                InlineKeyboardButton(
                    text=texts.BTN.PROFILE_EDIT_ABOUT,
                    callback_data=ProfileEditCB(field="about").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=texts.BTN.PROFILE_DELETE,
                    callback_data=ProfileDeleteCB(confirmed=False).pack(),
                )
            ],
        ]
    )


@router.message(F.chat.type == ChatType.PRIVATE, StateFilter(None), F.text == texts.BTN.PROFILE)
async def show_profile(message: Message, session: AsyncSession, db_user: User | None) -> None:
    if db_user is None:
        return
    await message.answer(
        await profile_service.render_profile(session, db_user), reply_markup=profile_kb()
    )


# --- Изменение полей ---

_EDIT_PROMPTS = {
    "nick": (
        ProfileForm.edit_nick,
        texts.PROFILE_EDIT_NICK_PROMPT.format(min=limits.NICK_MIN, max=limits.NICK_MAX),
    ),
    "group": (
        ProfileForm.edit_group,
        texts.PROFILE_EDIT_GROUP_PROMPT.format(max=limits.GROUP_MAX),
    ),
    "birth": (ProfileForm.edit_birth, texts.PROFILE_EDIT_BIRTH_PROMPT),
    "about": (
        ProfileForm.edit_about,
        texts.PROFILE_EDIT_ABOUT_PROMPT.format(min=limits.ABOUT_MIN, max=limits.ABOUT_MAX),
    ),
}


@router.callback_query(ProfileEditCB.filter())
async def cb_edit(
    callback: CallbackQuery, callback_data: ProfileEditCB, state: FSMContext, db_user: User | None
) -> None:
    if db_user is None or callback_data.field not in _EDIT_PROMPTS:
        await callback.answer()
        return
    new_state, prompt = _EDIT_PROMPTS[callback_data.field]
    await state.set_state(new_state)
    await callback.message.answer(prompt, reply_markup=form_cancel_kb())
    await callback.answer()


async def _saved(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User, field: str
) -> None:
    await profile_service.log_profile_update(session, db_user, field)
    await state.clear()
    await message.answer(texts.PROFILE_UPDATED, reply_markup=main_menu_kb(db_user))
    await message.answer(
        await profile_service.render_profile(session, db_user), reply_markup=profile_kb()
    )


@router.message(StateFilter(ProfileForm), F.text == texts.BTN.REG_CANCEL)
async def edit_cancel(message: Message, state: FSMContext, db_user: User | None) -> None:
    await state.clear()
    await message.answer(texts.BACK_TO_MENU_DONE, reply_markup=main_menu_kb(db_user))


@router.message(StateFilter(ProfileForm), CommandStart())
async def edit_start_over(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User | None
) -> None:
    await state.clear()
    await send_start_screen(message, session, db_user)


@router.message(ProfileForm.edit_nick, F.text, ~F.text.startswith("/"))
async def edit_nick(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    nick = message.text.strip()
    if not limits.NICK_MIN <= len(nick) <= limits.NICK_MAX or "\n" in nick:
        await message.answer(
            texts.REG_NAME_INVALID.format(min=limits.NICK_MIN, max=limits.NICK_MAX)
        )
        return
    db_user.display_name = nick
    await _saved(message, session, state, db_user, "display_name")


@router.message(ProfileForm.edit_group, F.text, ~F.text.startswith("/"))
async def edit_group(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    group = message.text.strip()
    if not 1 <= len(group) <= limits.GROUP_MAX:
        await message.answer(texts.REG_GROUP_INVALID)
        return
    db_user.university_group = group
    await _saved(message, session, state, db_user, "university_group")


@router.message(ProfileForm.edit_birth, F.text, ~F.text.startswith("/"))
async def edit_birth(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    try:
        birth_date = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
    except ValueError:
        await message.answer(texts.REG_BIRTH_INVALID)
        return
    age = (date.today() - birth_date).days // 365
    if age < 14 or age > 100:
        await message.answer(texts.REG_BIRTH_IMPLAUSIBLE)
        return
    db_user.birth_date = birth_date
    await _saved(message, session, state, db_user, "birth_date")


@router.message(ProfileForm.edit_about, F.text, ~F.text.startswith("/"))
async def edit_about(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    about = message.text.strip()
    if not limits.ABOUT_MIN <= len(about) <= limits.ABOUT_MAX:
        await message.answer(
            texts.REG_ABOUT_TOO_LONG.format(limit=limits.ABOUT_MAX, length=len(about))
            if len(about) > limits.ABOUT_MAX
            else texts.REG_ABOUT_TOO_SHORT.format(min=limits.ABOUT_MIN)
        )
        return
    db_user.about_text = about
    await _saved(message, session, state, db_user, "about_text")


# --- Удаление аккаунта ---


@router.callback_query(ProfileDeleteCB.filter(F.confirmed == False))  # noqa: E712
async def cb_delete_ask(callback: CallbackQuery, db_user: User | None) -> None:
    if db_user is None:
        await callback.answer()
        return
    await callback.message.answer(
        texts.PROFILE_DELETE_CONFIRM,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=texts.BTN.PROFILE_DELETE_YES,
                        callback_data=ProfileDeleteCB(confirmed=True).pack(),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=texts.BTN.PROFILE_DELETE_NO,
                        callback_data=ProfileEditCB(field="none").pack(),
                    )
                ],
            ]
        ),
    )
    await callback.answer()


@router.callback_query(ProfileDeleteCB.filter(F.confirmed == True))  # noqa: E712
async def cb_delete_do(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext, db_user: User | None
) -> None:
    if db_user is None:
        await callback.answer()
        return
    await state.clear()
    await profile_service.delete_account(session, callback.bot, db_user)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(texts.PROFILE_DELETED, reply_markup=main_menu_kb(None))
    await callback.answer()
