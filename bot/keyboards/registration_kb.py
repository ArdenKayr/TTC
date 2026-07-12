from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from bot import texts
from bot.db.models import University
from bot.keyboards.callback_data import UniversityPickCB

_CANCEL_ROW = [KeyboardButton(text=texts.BTN.REG_CANCEL)]


def _reply(rows: list[list[KeyboardButton]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def form_cancel_kb() -> ReplyKeyboardMarkup:
    """Меню обычного шага анкеты: только «Отмена»."""
    return _reply([_CANCEL_ROW])


def uni_menu_kb() -> ReplyKeyboardMarkup:
    """Меню шага вуза: сразу доступны оба «запасных выхода» и отмена."""
    return _reply(
        [
            [KeyboardButton(text=texts.BTN.UNI_NOT_LISTED)],
            [KeyboardButton(text=texts.BTN.UNI_NONE)],
            _CANCEL_ROW,
        ]
    )


def uni_search_inline_kb() -> InlineKeyboardMarkup:
    """Кнопка живого списка вузов (открывает inline-поиск в этом же чате)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BTN.UNI_SEARCH, switch_inline_query_current_chat=""
                )
            ]
        ]
    )


def university_results_kb(universities: list[University]) -> InlineKeyboardMarkup:
    """Результаты обычного (введённого сообщением) поиска — кнопки под сообщением."""
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
    return InlineKeyboardMarkup(inline_keyboard=rows)


def search_feedback_kb() -> ReplyKeyboardMarkup:
    """«Удобно ли было искать вуз?»"""
    return _reply(
        [
            [KeyboardButton(text=texts.BTN.UNI_FB_YES)],
            [KeyboardButton(text=texts.BTN.UNI_FB_NO)],
            _CANCEL_ROW,
        ]
    )


def alias_step_kb() -> ReplyKeyboardMarkup:
    """Сбор вариантов названий: «Готово» + отмена."""
    return _reply([[KeyboardButton(text=texts.BTN.ALIAS_DONE)], _CANCEL_ROW])


def confirm_kb() -> ReplyKeyboardMarkup:
    """Подтверждение анкеты."""
    return _reply(
        [
            [KeyboardButton(text=texts.BTN.REG_SUBMIT)],
            [KeyboardButton(text=texts.BTN.REG_RESTART), KeyboardButton(text=texts.BTN.REG_CANCEL)],
        ]
    )
