from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from bot import texts
from bot.db.models import User
from bot.enums import UserRole
from bot.keyboards.callback_data import AdminCallCB

_SUPER_ROLES = (UserRole.SUPERADMIN, UserRole.OWNER)


def _reply(rows: list[list[KeyboardButton]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выберите действие в меню",
    )


def main_menu_kb(user: User | None) -> ReplyKeyboardMarkup:
    """Постоянное меню внизу экрана (главный экран бота)."""
    if user is None:
        return _reply(
            [
                [KeyboardButton(text=texts.BTN.START_REGISTER)],
                [KeyboardButton(text=texts.BTN.START_ABOUT)],
            ]
        )
    rows = [
        [KeyboardButton(text=texts.BTN.INFO), KeyboardButton(text=texts.BTN.PROFILE)],
        [KeyboardButton(text=texts.BTN.ACT_NEW)],
        [KeyboardButton(text=texts.BTN.VOTE_NEW)],
        [KeyboardButton(text=texts.BTN.REPORT)],
    ]
    if user.current_role in _SUPER_ROLES:
        rows.append([KeyboardButton(text=texts.BTN.ADMIN_MODE)])
    return _reply(rows)


def info_menu_kb(is_superadmin: bool) -> ReplyKeyboardMarkup:
    """Подменю «Информация»: каждая кнопка — редактируемый блок контента."""
    rows = [
        [KeyboardButton(text=texts.BTN.START_ABOUT), KeyboardButton(text=texts.BTN.INFO_RULES)],
        [KeyboardButton(text=texts.BTN.INFO_DOCS), KeyboardButton(text=texts.BTN.INFO_UPDATES)],
        [
            KeyboardButton(text=texts.BTN.INFO_BECOME_ORG),
            KeyboardButton(text=texts.BTN.INFO_BECOME_ADMIN),
        ],
    ]
    if is_superadmin:
        rows.append([KeyboardButton(text=texts.BTN.INFO_ADMIN_REGS)])
    rows.append([KeyboardButton(text=texts.BTN.BACK_TO_MENU)])
    return _reply(rows)


def admin_panel_kb(is_owner: bool) -> ReplyKeyboardMarkup:
    """Меню режима «Админство» (суперадмины; у владельца кнопок больше)."""
    rows = [
        [KeyboardButton(text=texts.BTN.ADMIN_PANEL_USERS)],
        [KeyboardButton(text=texts.BTN.ADMIN_PANEL_CRUD)],
        [KeyboardButton(text=texts.BTN.ADMIN_PANEL_SCENARIOS)],
    ]
    if is_owner:
        rows.append(
            [
                KeyboardButton(text=texts.BTN.ADMIN_PANEL_LOGS),
                KeyboardButton(text=texts.BTN.ADMIN_PANEL_UPDATES),
            ]
        )
    rows.append([KeyboardButton(text=texts.BTN.ADMIN_PANEL_USER_MODE)])
    return _reply(rows)


def admin_call_kb() -> InlineKeyboardMarkup:
    """«Возьмусь» под вызовом админов — чтобы на один вызов не бежали все сразу."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.BTN.CALL_CLAIM, callback_data=AdminCallCB().pack())]
        ]
    )
