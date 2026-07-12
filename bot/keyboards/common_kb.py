from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from bot import texts


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
