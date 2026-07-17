from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from bot import texts
from bot.keyboards.callback_data import AdminCallCB


def main_menu_kb(registered: bool) -> ReplyKeyboardMarkup:
    """Постоянное меню внизу экрана (главный экран бота)."""
    rows = []
    if not registered:
        rows.append([KeyboardButton(text=texts.BTN.START_REGISTER)])
    rows.append([KeyboardButton(text=texts.BTN.START_ABOUT)])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выберите действие в меню",
    )


def admin_call_kb() -> InlineKeyboardMarkup:
    """«Возьмусь» под вызовом админов — чтобы на один вызов не бежали все сразу."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.BTN.CALL_CLAIM, callback_data=AdminCallCB().pack())]
        ]
    )
