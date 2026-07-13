from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from bot import limits, texts
from bot.db.models import University
from bot.keyboards.callback_data import NoopCB, UniPageCB, UniShowAllCB, UniversityPickCB

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


def university_browser_kb(
    universities: list[University], page: int, pages: int, filtered: bool
) -> InlineKeyboardMarkup | None:
    """Кнопки листаемого списка вузов: номера (полные названия — в тексте сообщения).

    Нумерация сквозная по страницам, кнопки по 4 в ряд.
    filtered=True — список сужен запросом, добавляется «Показать все вузы».
    Возвращает None, если показывать нечего (пустой справочник).
    """
    rows = []
    number_row: list[InlineKeyboardButton] = []
    for i, uni in enumerate(universities):
        number = page * limits.UNI_PAGE_SIZE + i + 1
        number_row.append(
            InlineKeyboardButton(
                text=str(number),
                callback_data=UniversityPickCB(university_id=uni.university_id).pack(),
            )
        )
        if len(number_row) == 4:
            rows.append(number_row)
            number_row = []
    if number_row:
        rows.append(number_row)
    if pages > 1:
        nav = []
        if page > 0:
            nav.append(
                InlineKeyboardButton(
                    text=texts.BTN.UNI_PAGE_PREV, callback_data=UniPageCB(page=page - 1).pack()
                )
            )
        # Неактивный счётчик страниц между стрелками.
        nav.append(
            InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data=NoopCB().pack())
        )
        if page < pages - 1:
            nav.append(
                InlineKeyboardButton(
                    text=texts.BTN.UNI_PAGE_NEXT, callback_data=UniPageCB(page=page + 1).pack()
                )
            )
        rows.append(nav)
    if filtered:
        rows.append(
            [InlineKeyboardButton(text=texts.BTN.UNI_SHOW_ALL, callback_data=UniShowAllCB().pack())]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


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
