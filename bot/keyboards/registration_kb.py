from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

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
                text="➕ Моего вуза нет в списке", callback_data=UniversityNewCB().pack()
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Отправить", callback_data=RegFormCB(action="submit").pack()
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Заполнить заново", callback_data=RegFormCB(action="restart").pack()
                ),
                InlineKeyboardButton(
                    text="🚫 Отмена", callback_data=RegFormCB(action="cancel").pack()
                ),
            ],
        ]
    )
