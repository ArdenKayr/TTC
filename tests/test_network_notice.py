"""Сбой связи не оставляет человека в тишине.

Написано по записи №14 в журнале боевых ошибок (13 сентября 2026, 22:10 МСК):
человек ввёл ник, вопрос про вуз не дождался ответа Telegram, и бот замолчал.
Анкету слой form_guard вернул на шаг «ник», но сам человек об этом не узнал:
он смотрел на пустой экран и не понимал, ждать ему или писать снова.

Проверяется, кому бот говорит «связь подвела — повторите» и кому нет. Граница
важна не меньше самого правила: настоящая ошибка в коде на повторе упадёт так
же, а в группе сорвалось действие одного, а сообщение увидели бы все.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError

from bot import texts
from bot.services import error_service

PERSON = 1673238859


class _Bot:
    """Подставной бот: запоминает, кому и что отправлено."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text))


class _DeadBot(_Bot):
    """Связи нет и для самого предупреждения — как оно при сбое и бывает."""

    async def send_message(self, chat_id, text, **kwargs):
        raise _timeout()


def _timeout() -> TelegramNetworkError:
    return TelegramNetworkError(method=None, message="Request timeout error")


def _event(exception: Exception, *, chat_type: str = "private", pressed: bool = False):
    """Событие ошибки: сообщение или нажатие кнопки в чате нужного вида."""
    message = SimpleNamespace(
        chat=SimpleNamespace(id=PERSON, type=chat_type),
        from_user=SimpleNamespace(id=PERSON),
        text="myco",
        caption=None,
    )
    if pressed:
        query = SimpleNamespace(from_user=message.from_user, message=message, data="pick:1")
        update = SimpleNamespace(message=None, edited_message=None, callback_query=query)
    else:
        update = SimpleNamespace(message=message, edited_message=None, callback_query=None)
    return SimpleNamespace(update=update, exception=exception)


# --- Кому говорим ---


def test_network_failure_in_private_chat_is_explained() -> None:
    """Ровно случай №14: бот не ответил на сообщение — человек узнаёт почему."""
    bot = _Bot()
    asyncio.run(error_service.warn_person(bot, _event(_timeout())))
    assert bot.sent == [(PERSON, texts.NETWORK_TROUBLE_NOTICE)]


def test_network_failure_on_button_press_is_explained() -> None:
    """Сорвалось нажатие кнопки — предупреждение приходит в тот же чат."""
    bot = _Bot()
    asyncio.run(error_service.warn_person(bot, _event(_timeout(), pressed=True)))
    assert bot.sent == [(PERSON, texts.NETWORK_TROUBLE_NOTICE)]


# --- Кому не говорим ---


@pytest.mark.parametrize(
    "exception",
    [
        ValueError("ошибка в коде"),
        TelegramBadRequest(method=None, message="Bad Request: chat not found"),
    ],
    ids=["ошибка в коде", "отказ Telegram"],
)
def test_real_errors_do_not_ask_to_repeat(exception: Exception) -> None:
    """Настоящая ошибка на повторе упадёт снова — просить повторить нечестно."""
    assert error_service.chat_to_warn(_event(exception)) is None


def test_group_chat_is_not_disturbed() -> None:
    """В группе сорвалось действие одного, а сообщение увидели бы все."""
    assert error_service.chat_to_warn(_event(_timeout(), chat_type="supergroup")) is None


def test_update_without_chat_is_skipped() -> None:
    """Событие не из переписки (например, смена прав бота) — говорить некому."""
    update = SimpleNamespace(message=None, edited_message=None, callback_query=None)
    event = SimpleNamespace(update=update, exception=_timeout())
    assert error_service.chat_to_warn(event) is None


# --- Надёжность ---


def test_failed_warning_does_not_break_error_handling() -> None:
    """Связи нет и для предупреждения — обработка ошибки идёт дальше молча."""
    asyncio.run(error_service.warn_person(_DeadBot(), _event(_timeout())))


def test_person_is_warned_even_if_journal_is_broken(monkeypatch: pytest.MonkeyPatch) -> None:
    """Человек ждёт ответа — его предупреждение не зависит от записи в журнал."""

    async def broken_journal(*args, **kwargs):
        raise RuntimeError("база недоступна")

    monkeypatch.setattr(error_service, "_persist_and_notify", broken_journal)
    bot = _Bot()
    handled = asyncio.run(error_service.on_error(_event(_timeout()), bot))
    assert handled is True, "Ошибка должна считаться обработанной, иначе aiogram поднимет её выше."
    assert bot.sent == [(PERSON, texts.NETWORK_TROUBLE_NOTICE)]
