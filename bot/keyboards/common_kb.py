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

# Тексты всех реплай-кнопок меню: FSM-формы игнорируют их как «значение»
# (нажатие кнопки меню посреди ввода отменяет форму, а не сохраняется).
MENU_BUTTON_TEXTS = {
    texts.BTN.INFO,
    texts.BTN.PROFILE,
    texts.BTN.REPORT,
    texts.BTN.ACT_NEW,
    texts.BTN.VOTE_NEW,
    texts.BTN.ADMIN_MODE,
    texts.BTN.ADMIN_PANEL_USERS,
    texts.BTN.ADMIN_PANEL_CRUD,
    texts.BTN.ADMIN_PANEL_SCENARIOS,
    texts.BTN.ADMIN_PANEL_CONTENT,
    texts.BTN.ADMIN_PANEL_LOGS,
    texts.BTN.ADMIN_PANEL_UPDATES,
    texts.BTN.ADMIN_PANEL_USER_MODE,
}


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
    # Компактно: по две кнопки в ряд, всё меню видно без пролистывания.
    third_row = [KeyboardButton(text=texts.BTN.REPORT)]
    if user.current_role in _SUPER_ROLES:
        third_row.append(KeyboardButton(text=texts.BTN.ADMIN_MODE))
    return _reply(
        [
            [KeyboardButton(text=texts.BTN.INFO), KeyboardButton(text=texts.BTN.PROFILE)],
            [KeyboardButton(text=texts.BTN.ACT_NEW), KeyboardButton(text=texts.BTN.VOTE_NEW)],
            third_row,
        ]
    )


def info_menu_kb(is_superadmin: bool) -> ReplyKeyboardMarkup:
    """Подменю «Информация»: каждая кнопка — редактируемый блок контента."""
    last_row = [KeyboardButton(text=texts.BTN.BACK_TO_MENU)]
    if is_superadmin:
        last_row.insert(0, KeyboardButton(text=texts.BTN.INFO_ADMIN_REGS))
    return _reply(
        [
            # Инструкция — во всю ширину и первой строкой: это то, с чего человеку
            # проще всего начать, когда он не понимает, что вообще умеет бот.
            [KeyboardButton(text=texts.BTN.INFO_GUIDE)],
            [KeyboardButton(text=texts.BTN.START_ABOUT), KeyboardButton(text=texts.BTN.INFO_RULES)],
            [KeyboardButton(text=texts.BTN.INFO_DOCS), KeyboardButton(text=texts.BTN.INFO_UPDATES)],
            [
                KeyboardButton(text=texts.BTN.INFO_BECOME_ORG),
                KeyboardButton(text=texts.BTN.INFO_BECOME_ADMIN),
            ],
            last_row,
        ]
    )


def admin_panel_kb(is_owner: bool) -> ReplyKeyboardMarkup:
    """Меню режима «Админство» (суперадмины; у владельца кнопок больше)."""
    rows = [
        [
            KeyboardButton(text=texts.BTN.ADMIN_PANEL_USERS),
            KeyboardButton(text=texts.BTN.ADMIN_PANEL_CRUD),
        ]
    ]
    # «Сценарии» и «Разделы» — соседи не случайно: это два редактора текстов
    # бота. Сценарии — что бот отвечает на действия, Разделы — страницы меню
    # «Информация». Раньше вторые открывались только командой /content, и найти
    # их, не зная команду, было нельзя.
    rows.append(
        [
            KeyboardButton(text=texts.BTN.ADMIN_PANEL_SCENARIOS),
            KeyboardButton(text=texts.BTN.ADMIN_PANEL_CONTENT),
        ]
    )
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
