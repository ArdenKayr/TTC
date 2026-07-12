from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import texts
from bot.keyboards.callback_data import StartCB


def start_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BTN.START_REGISTER,
                    callback_data=StartCB(action="register").pack(),
                ),
                InlineKeyboardButton(
                    text=texts.BTN.START_ABOUT,
                    callback_data=StartCB(action="about").pack(),
                ),
            ]
        ]
    )
