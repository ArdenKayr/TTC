"""Почему сообщение не подошло — словами, понятными человеку.

Молчание бота неотличимо от поломки: человек не понимает, дошло ли сообщение,
работает ли бот и надо ли повторять. Поэтому у каждого ожидания есть ответ на
любой ввод, а этот модуль отвечает на один вопрос — что именно пришло и что с
этим не так.

Сам ответ ничего не решает за шаг: он только объясняет. Повторный вопрос шага
задаёт роутер — так человек сразу видит, что от него ждут.
"""

from __future__ import annotations

from aiogram.types import Message

from bot import texts

# У сообщения бывает несколько полей сразу (фото с подписью — это и photo, и
# caption), поэтому берём первое совпавшее: важен вид вложения, а не текст при нём.
_KINDS = (
    "photo",
    "video",
    "video_note",
    "animation",
    "audio",
    "voice",
    "document",
    "sticker",
    "location",
    "contact",
    "poll",
    "dice",
)


def kind(message: Message) -> str:
    """Как назвать присланное по-человечески (винительный падеж: «прислали …»)."""
    for name in _KINDS:
        if getattr(message, name, None) is not None:
            return texts.INPUT_KINDS[name]
    return texts.INPUT_KIND_UNKNOWN


def is_command(message: Message) -> bool:
    """Похоже на команду — «/что-то».

    Команд у бота нет, но люди их всё равно пробуют, и раньше бот на них молчал.
    """
    return bool(message.text and message.text.startswith("/"))


def form_explain(message: Message, *, files_ok: bool = False) -> str:
    """Ответ шага анкеты на то, что он принять не может.

    files_ok=True — шаг принимает и вложения (редактор разделов, сценарии,
    пост обновления), там про «только текст» говорить нельзя.
    """
    if is_command(message):
        return texts.FORM_INPUT_COMMAND
    if message.text:
        # Текст дошёл, но шаг ждёт выбора кнопкой — например «Анонимный опрос?».
        return texts.FORM_INPUT_NEEDS_BUTTON
    template = texts.FORM_INPUT_WITH_FILES if files_ok else texts.FORM_INPUT_ONLY_TEXT
    return template.format(kind=kind(message))


def menu_explain(message: Message) -> str:
    """Ответ вне анкеты: бот ждёт кнопку меню, а пришло что-то другое."""
    if is_command(message):
        return texts.MENU_INPUT_COMMAND
    if message.text:
        return texts.MENU_INPUT_TEXT
    return texts.MENU_INPUT_UNKNOWN.format(kind=kind(message))
