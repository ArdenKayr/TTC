"""Главное меню зарегистрированного: «Информация», «Репорт», «Админство».

Каждая кнопка «Информации» показывает редактируемый блок контента
(/content); «Админские регламенты» видят только суперадмины и владелец.
Режим «Админство» меняет только меню — команды работают всегда.
"""

from html import escape

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import limits, texts
from bot.db.models import User
from bot.enums import UserRole
from bot.keyboards.activity_kb import form_cancel_kb
from bot.keyboards.common_kb import admin_panel_kb, info_menu_kb, main_menu_kb
from bot.routers.common import send_start_screen
from bot.services import content_service, notification_service, scenario_service
from bot.states.profile_states import ReportForm

router = Router(name="user_menu")

_SUPER_ROLES = (UserRole.SUPERADMIN, UserRole.OWNER)
_PRIVATE = F.chat.type == ChatType.PRIVATE

# Кнопка подменю «Информация» -> слот контента.
_INFO_SLOTS = {
    texts.BTN.INFO_RULES: "rules",
    texts.BTN.INFO_DOCS: "docs",
    texts.BTN.INFO_UPDATES: "updates",
    texts.BTN.INFO_BECOME_ORG: "become_organizer",
    texts.BTN.INFO_BECOME_ADMIN: "become_admin",
}


def _is_super(db_user: User | None) -> bool:
    return db_user is not None and db_user.current_role in _SUPER_ROLES


# --- Информация ---


@router.message(_PRIVATE, StateFilter(None), F.text == texts.BTN.INFO)
async def info_menu(message: Message, db_user: User | None) -> None:
    if db_user is None:
        return
    await message.answer(texts.INFO_PICK, reply_markup=info_menu_kb(_is_super(db_user)))


@router.message(_PRIVATE, StateFilter(None), F.text.in_(set(_INFO_SLOTS)))
async def info_show(message: Message, session: AsyncSession, db_user: User | None) -> None:
    if db_user is None:
        return
    content = await content_service.get_content(session, _INFO_SLOTS[message.text])
    await content_service.send_content(message, content)


@router.message(_PRIVATE, StateFilter(None), F.text == texts.BTN.INFO_ADMIN_REGS)
async def info_admin_regs(message: Message, session: AsyncSession, db_user: User | None) -> None:
    if db_user is None:
        return
    if not _is_super(db_user):
        await message.answer(texts.INFO_NO_ACCESS)
        return
    content = await content_service.get_content(session, "admin_regulations")
    await content_service.send_content(message, content)


@router.message(_PRIVATE, StateFilter(None), F.text == texts.BTN.BACK_TO_MENU)
async def back_to_menu(message: Message, db_user: User | None) -> None:
    await message.answer(texts.BACK_TO_MENU_DONE, reply_markup=main_menu_kb(db_user))


# --- Репорт кнопкой ---


@router.message(_PRIVATE, StateFilter(None), F.text == texts.BTN.REPORT)
async def report_start(message: Message, state: FSMContext, db_user: User | None) -> None:
    if db_user is None:
        await message.answer(texts.REPORT_NOT_REGISTERED)
        return
    await state.set_state(ReportForm.text)
    await message.answer(
        texts.REPORT_PROMPT.format(min=limits.REPORT_MIN, max=limits.REPORT_MAX),
        reply_markup=form_cancel_kb(),
    )


@router.message(ReportForm.text, F.text == texts.BTN.REG_CANCEL)
async def report_cancel(message: Message, state: FSMContext, db_user: User | None) -> None:
    await state.clear()
    await message.answer(texts.BACK_TO_MENU_DONE, reply_markup=main_menu_kb(db_user))


@router.message(ReportForm.text, CommandStart())
async def report_start_over(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User | None
) -> None:
    await state.clear()
    await send_start_screen(message, session, db_user)


@router.message(ReportForm.text, F.text, ~F.text.startswith("/"))
async def report_text(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User | None
) -> None:
    if db_user is None:
        await state.clear()
        return
    text = message.text.strip()
    if not limits.REPORT_MIN <= len(text) <= limits.REPORT_MAX:
        await message.answer(
            texts.REPORT_INVALID.format(min=limits.REPORT_MIN, max=limits.REPORT_MAX)
        )
        return
    await state.clear()
    username = f"@{db_user.username}" if db_user.username else f"id {db_user.tg_id}"
    await notification_service.send_admin_report(
        message.bot,
        texts.REPORT_CARD.format(
            name=escape(db_user.display_name), username=escape(username), text=escape(text)
        ),
    )
    await scenario_service.reply(message, session, "report_sent", main_menu_kb(db_user))


# --- Режим «Админство» (только меню, команды работают всегда) ---


@router.message(_PRIVATE, StateFilter(None), F.text == texts.BTN.ADMIN_MODE)
async def admin_mode_on(message: Message, db_user: User | None) -> None:
    if not _is_super(db_user):
        return
    await message.answer(
        texts.ADMIN_MODE_ON,
        reply_markup=admin_panel_kb(db_user.current_role == UserRole.OWNER),
    )


@router.message(_PRIVATE, StateFilter(None), F.text == texts.BTN.ADMIN_PANEL_USER_MODE)
async def admin_mode_off(message: Message, db_user: User | None) -> None:
    await message.answer(texts.ADMIN_MODE_OFF, reply_markup=main_menu_kb(db_user))


# «Пользователи» — routers/superadmin.py; «CRUD» — admin/crud_admin.py;
# «Сценарии» — admin/scenario_admin.py. Заглушки — только до блока D.
@router.message(
    _PRIVATE,
    StateFilter(None),
    F.text.in_(
        {
            texts.BTN.ADMIN_PANEL_LOGS,
            texts.BTN.ADMIN_PANEL_UPDATES,
        }
    ),
)
async def admin_panel_wip(message: Message, db_user: User | None) -> None:
    if not _is_super(db_user):
        return
    await message.answer(texts.ADMIN_PANEL_WIP)
