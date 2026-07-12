from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import texts
from bot.db.models import University
from bot.keyboards.callback_data import (
    AliasDoneCB,
    RegFormCB,
    SearchFeedbackCB,
    UniversityNewCB,
    UniversityNoneCB,
    UniversityPickCB,
)


def _no_university_row() -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(text=texts.BTN.UNI_NONE, callback_data=UniversityNoneCB().pack())
    ]


def university_prompt_kb() -> InlineKeyboardMarkup:
    """Показывается вместе с просьбой ввести название вуза."""
    return InlineKeyboardMarkup(inline_keyboard=[_no_university_row()])


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
    rows.append(_no_university_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def search_feedback_kb() -> InlineKeyboardMarkup:
    """«Удобно ли было искать вуз?» — Да / Нет, добавить вариант поиска."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BTN.UNI_FB_YES,
                    callback_data=SearchFeedbackCB(action="yes").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=texts.BTN.UNI_FB_NO,
                    callback_data=SearchFeedbackCB(action="no").pack(),
                )
            ],
        ]
    )


def alias_done_kb() -> InlineKeyboardMarkup:
    """Кнопка «Готово» при сборе вариантов названий (по одному сообщению)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.BTN.ALIAS_DONE, callback_data=AliasDoneCB().pack())]
        ]
    )


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
