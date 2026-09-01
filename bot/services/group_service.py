"""Как понимать отказы Telegram при работе с группой.

Отказ отказу рознь. «Бот не админ» и «связь не дошла» — поломки, их надо
чинить. А «нельзя исключить создателя группы» — правило самого Telegram:
создателя не выгонит ни бот, ни человек, никакими правами. Записывать такое
в журнал теми же словами, что и настоящий сбой, — значит звать владельца
чинить то, чего чинить нельзя. Чем больше таких ложных тревог, тем меньше
внимания настоящим.
"""

from aiogram.exceptions import TelegramAPIError

from bot import texts

# Отдельного кода ошибки у Telegram для этого случая нет — только текст
# ответа, по нему и узнаём.
_CHAT_OWNER_REFUSAL = "can't remove chat owner"


def is_chat_owner_refusal(error: TelegramAPIError) -> bool:
    """Telegram отказал потому, что человек — создатель группы?"""
    return _CHAT_OWNER_REFUSAL in str(error).lower()


def describe_removal_failure(error: TelegramAPIError, done: str) -> str:
    """Почему человек остался в группе — словами, понятными без кода.

    `done` — что бот всё-таки успел сделать. Из записи в журнале должно быть
    видно и сделанное, и несделанное: роль сменилась, а из группы человек
    не вышел — это разные половины одного действия.
    """
    if is_chat_owner_refusal(error):
        return texts.NOTE_REMOVE_CHAT_OWNER.format(done=done)
    return texts.NOTE_REMOVE_FAILED.format(done=done, error=error)
