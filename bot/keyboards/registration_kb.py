from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import texts
from bot.db.models import University
from bot.keyboards.callback_data import RegFormCB, UniversityNewCB, UniversityPickCB


def university_results_kb(universities: list[University]) -> InlineKeyboardMarkup:
    rows = []
    for uni in universities:
        label = uni.canonical_name
        if uni.city:
            label += f" ({uni.city})"
        if len(label) > 60:
            label = label[:57] + "..."
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=UniversityPickCB(university_id=uni.university_id).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=texts.BTN.UNI_NOT_LISTED, callback_data=UniversityNewCB().pack()
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BTN.REG_SUBMIT, callback_data=RegFormCB(action="submit").pack()
                )
            ],
            [
                InlineKeyboardButton(
                    text=texts.BTN.REG_RESTART, callback_data=RegFormCB(action="restart").pack()
                ),
                InlineKeyboardButton(
                    text=texts.BTN.REG_CANCEL, callback_data=RegFormCB(action="cancel").pack()
                ),
            ],
        ]
    )
