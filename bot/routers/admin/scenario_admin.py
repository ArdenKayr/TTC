"""«Разработка сценариев»: суперадмины меняют тексты-реакции бота без кода.

Кнопка «Сценарии» в панели Админства → раздел → сообщение → новый
текст/фото/документ. «Сбросить к стандартному» возвращает текст из кода.
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
from bot.filters.role_filter import IsSuperadmin
from bot.keyboards.callback_data import ScenActionCB, ScenGroupCB, ScenKeyCB
from bot.keyboards.common_kb import MENU_BUTTON_TEXTS as _MENU_BUTTONS
from bot.routers.common import send_start_screen
from bot.services import content_service, input_guard, scenario_service
from bot.states.content_states import ScenarioEditForm

router = Router(name="scenario_admin")
router.message.filter(IsSuperadmin())
router.callback_query.filter(IsSuperadmin())

_PRIVATE = F.chat.type == ChatType.PRIVATE


def _groups_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=group, callback_data=ScenGroupCB(g=i).pack())]
        for i, group in enumerate(scenario_service.GROUPS)
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _keys_kb(group: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=scen.title, callback_data=ScenKeyCB(key=scen.key).pack())]
        for scen in scenario_service.SCENARIOS.values()
        if scen.group == group
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _edit_kb(key: str, has_file: bool) -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton(
            text=texts.BTN.SCEN_RESET, callback_data=ScenActionCB(action="reset", key=key).pack()
        )
    ]
    if has_file:
        row.append(
            InlineKeyboardButton(
                text=texts.BTN.CONTENT_REMOVE_FILE,
                callback_data=ScenActionCB(action="rmfile", key=key).pack(),
            )
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            row,
            [
                InlineKeyboardButton(
                    text=texts.BTN.SCEN_BACK,
                    callback_data=ScenActionCB(action="back", key=key).pack(),
                )
            ],
        ]
    )


async def _show_scenario(message: Message, session: AsyncSession, key: str) -> None:
    scen = scenario_service.SCENARIOS[key]
    content, customized = await scenario_service.raw(session, key)
    text = texts.SCEN_CURRENT.format(title=escape(scen.title), text=escape(content.text))
    if customized:
        text += texts.SCEN_CUSTOM_MARK
    if scen.params:
        text += texts.SCEN_PARAMS_HINT.format(
            params=", ".join("{" + p + "}" for p in scen.params)
        )
    if content.file_id is not None:
        text += texts.SCEN_HAS_FILE.format(file_type=content.file_type)
    await message.answer(text, reply_markup=_edit_kb(key, content.file_id is not None))
    await message.answer(texts.SCEN_PROMPT)


@router.message(_PRIVATE, StateFilter(None), F.text == texts.BTN.ADMIN_PANEL_SCENARIOS)
async def scen_home(message: Message) -> None:
    await message.answer(texts.SCEN_PICK_GROUP, reply_markup=_groups_kb())


@router.callback_query(ScenGroupCB.filter())
async def cb_group(callback: CallbackQuery, callback_data: ScenGroupCB) -> None:
    if not 0 <= callback_data.g < len(scenario_service.GROUPS):
        await callback.answer(texts.SCEN_UNKNOWN, show_alert=True)
        return
    group = scenario_service.GROUPS[callback_data.g]
    await callback.message.answer(
        texts.SCEN_PICK_KEY.format(group=group), reply_markup=_keys_kb(group)
    )
    await callback.answer()


@router.callback_query(ScenKeyCB.filter())
async def cb_key(
    callback: CallbackQuery, callback_data: ScenKeyCB, session: AsyncSession, state: FSMContext
) -> None:
    if callback_data.key not in scenario_service.SCENARIOS:
        await callback.answer(texts.SCEN_UNKNOWN, show_alert=True)
        return
    await state.set_state(ScenarioEditForm.waiting)
    await state.update_data(key=callback_data.key)
    await _show_scenario(callback.message, session, callback_data.key)
    await callback.answer()


@router.callback_query(ScenActionCB.filter())
async def cb_action(
    callback: CallbackQuery,
    callback_data: ScenActionCB,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    key = callback_data.key
    if key not in scenario_service.SCENARIOS:
        await callback.answer(texts.SCEN_UNKNOWN, show_alert=True)
        return
    if callback_data.action == "back":
        await state.clear()
        group = scenario_service.SCENARIOS[key].group
        await callback.message.answer(
            texts.SCEN_PICK_KEY.format(group=group), reply_markup=_keys_kb(group)
        )
    elif callback_data.action == "reset":
        await scenario_service.reset(session, db_user, key)
        await callback.message.answer(texts.SCEN_RESET_DONE)
        await _show_scenario(callback.message, session, key)
    elif callback_data.action == "rmfile":
        await scenario_service.remove_file(session, db_user, key)
        await callback.message.answer(texts.SCEN_FILE_REMOVED)
        await _show_scenario(callback.message, session, key)
    await callback.answer()


@router.message(ScenarioEditForm.waiting, CommandStart())
async def scen_start_over(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User | None
) -> None:
    await state.clear()
    await send_start_screen(message, session, db_user)


@router.message(ScenarioEditForm.waiting, F.text.in_(_MENU_BUTTONS))
async def scen_menu_pressed(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.CONTENT_CANCELLED)


async def _preview(message: Message, session: AsyncSession, key: str) -> None:
    content, _ = await scenario_service.raw(session, key)
    try:
        await content_service.send_content(message, content)
    except Exception:
        await message.answer(texts.SCEN_SAVED_BAD_HTML)


@router.message(ScenarioEditForm.waiting, F.photo)
async def scen_new_photo(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    data = await state.get_data()
    await scenario_service.set_file(
        session,
        db_user,
        data["key"],
        file_id=message.photo[-1].file_id,
        file_type="photo",
        caption=content_service.formatted_text(message) or None,
    )
    await state.clear()
    await message.answer(texts.SCEN_SAVED)
    await _preview(message, session, data["key"])


@router.message(ScenarioEditForm.waiting, F.document)
async def scen_new_document(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    data = await state.get_data()
    await scenario_service.set_file(
        session,
        db_user,
        data["key"],
        file_id=message.document.file_id,
        file_type="document",
        caption=content_service.formatted_text(message) or None,
    )
    await state.clear()
    await message.answer(texts.SCEN_SAVED)
    await _preview(message, session, data["key"])


@router.message(ScenarioEditForm.waiting, F.text, ~F.text.startswith("/"))
async def scen_new_text(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    text = content_service.formatted_text(message)
    if not scenario_service.validate_template(text):
        await message.answer(texts.SCEN_BAD_BRACES)
        return
    if scenario_service.has_split_placeholder(text):
        await message.answer(texts.SCEN_SPLIT_PLACEHOLDER)
        return
    data = await state.get_data()
    await scenario_service.set_text(session, db_user, data["key"], text)
    await state.clear()
    await message.answer(texts.SCEN_SAVED)
    await _preview(message, session, data["key"])


@router.message(ScenarioEditForm.waiting)
async def msg_unexpected(message: Message) -> None:
    """Ответ на то, что редактор сценария принять не может: стикер, голосовое.

    Стоит последним в роутере: текст, фото и файл разбирают обработчики выше.
    Карточку сценария не переспрашиваем — она уже висит выше в переписке,
    хватает напоминания, что прислать.
    """
    await message.answer(input_guard.form_explain(message, files_ok=True))
    await message.answer(texts.SCEN_PROMPT)
