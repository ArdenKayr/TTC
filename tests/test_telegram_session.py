"""Связь с Telegram: не ждать мёртвый маршрут и не задваивать сообщения.

Из журнала контейнера на бою (01.09.2026):

    Update id=492159888 is handled. Duration 60622 ms

Ровно минута — столько библиотека по умолчанию ждёт ответа. Человек в это
время смотрит на молчащего бота. Причина снаружи: с этого сервера
api.telegram.org доступен по IPv6 и недоступен по IPv4, а когда IPv6 на
секунды пропадает, запрос уходит в мёртвый IPv4 и виснет до конца таймаута.

Здесь проверяется наша половина дела: ожидание ограничено, ненужный
протокол можно запретить совсем, а короткие провалы бот переживает
повтором — но только там, где повтор не обернётся вторым сообщением
человеку.
"""

from __future__ import annotations

import asyncio
import socket

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError

from bot import telegram_session
from bot.telegram_session import (
    CONNECT_TIMEOUT,
    RETRIES,
    TOTAL_TIMEOUT,
    TelegramSession,
    looks_like_no_connection,
)


class _Method:
    """Любой вызов Telegram — для журнала важно только его имя."""

    __api_method__ = "sendMessage"


def _run(make_request, monkeypatch) -> object:
    """Прогоняет запрос через повторы, не тратя на паузы настоящее время."""
    monkeypatch.setattr(telegram_session, "RETRY_PAUSE", 0)
    return asyncio.run(
        telegram_session.retry_on_lost_connection(make_request, bot=None, method=_Method())
    )


def test_ipv6_only_refuses_the_dead_route() -> None:
    """Запрет IPv4 — это отказ вместо минутного ожидания в никуда."""
    session = TelegramSession("ipv6")
    assert session._connector_init["family"] == socket.AF_INET6


def test_auto_leaves_the_choice_to_the_system() -> None:
    """По умолчанию ничего не навязываем: на других машинах IPv4 живой."""
    session = TelegramSession("auto")
    assert "family" not in session._connector_init


def test_unknown_family_explains_itself() -> None:
    """Ошибку в настройках читает владелец, а не программист."""
    with pytest.raises(ValueError) as error:
        TelegramSession("ipv7")
    assert "TELEGRAM_IP_FAMILY" in str(error.value)
    assert "ipv6" in str(error.value), "Надо назвать допустимые значения."


def test_waiting_is_limited() -> None:
    """Минута ожидания — это минута молчания бота для живого человека."""
    session = TelegramSession("auto")
    assert session.request_timeout.total == TOTAL_TIMEOUT
    assert session.request_timeout.sock_connect == CONNECT_TIMEOUT
    assert TOTAL_TIMEOUT < 60, "Смысл всей затеи — ждать заметно меньше умолчания."


def test_polling_can_still_do_arithmetic_on_the_timeout() -> None:
    """`session.timeout` обязан остаться числом.

    Опрос событий складывает его со своим сроком ожидания
    (`int(bot.session.timeout + polling_timeout)`). Объект на этом месте
    роняет бота при старте — проверено на бою 02.09.2026, контейнер ушёл
    в цикл перезапуска сразу после выкатки.
    """
    session = TelegramSession("auto")
    assert int(session.timeout + 30) == int(TOTAL_TIMEOUT) + 30


def test_ordinary_requests_get_our_timeouts(monkeypatch) -> None:
    """Свои сроки подставляются туда, где библиотека их не назвала."""
    seen = {}

    async def fake_make_request(self, bot, method, timeout=None):
        seen["timeout"] = timeout

    monkeypatch.setattr(
        telegram_session.AiohttpSession, "make_request", fake_make_request, raising=True
    )
    session = TelegramSession("auto")
    asyncio.run(session.make_request(bot=None, method=_Method()))
    assert seen["timeout"] is session.request_timeout

    asyncio.run(session.make_request(bot=None, method=_Method(), timeout=50))
    assert seen["timeout"] == 50, "Ожидание опроса событий трогать нельзя."


def test_connection_phase_is_told_by_time() -> None:
    """Не дозвонились или ответ не вернулся — библиотека зовёт это одинаково.

    Различаем по времени: на соединение отведено меньше, чем на весь запрос.
    """
    assert looks_like_no_connection(0.2) is True
    assert looks_like_no_connection(TOTAL_TIMEOUT) is False


def test_short_outage_is_survived_by_a_retry(monkeypatch) -> None:
    """Провалы связи короткие — вторая попытка обычно проходит."""
    calls = []

    async def make_request(bot, method):
        calls.append(1)
        if len(calls) == 1:
            raise TelegramNetworkError(method=None, message="Request timeout error")
        return "ответ Telegram"

    assert _run(make_request, monkeypatch) == "ответ Telegram"
    assert len(calls) == 2


def test_no_retry_when_the_message_may_have_arrived(monkeypatch) -> None:
    """Ответ не вернулся — но сообщение могло дойти. Повтор задвоит его.

    Второе одинаковое сообщение человеку хуже, чем честная ошибка админу:
    ошибку видно и можно повторить руками, а дубль уже не отозвать.
    """
    calls = []

    async def make_request(bot, method):
        calls.append(1)
        raise TelegramNetworkError(method=None, message="Request timeout error")

    monkeypatch.setattr(telegram_session, "looks_like_no_connection", lambda elapsed: False)
    with pytest.raises(TelegramNetworkError):
        _run(make_request, monkeypatch)
    assert len(calls) == 1, "Запрос, который мог дойти, повторять нельзя."


def test_gives_up_after_all_attempts(monkeypatch) -> None:
    """Связи нет совсем — бот сдаётся и говорит об этом, а не молчит вечно."""
    calls = []

    async def make_request(bot, method):
        calls.append(1)
        raise TelegramNetworkError(method=None, message="Request timeout error")

    with pytest.raises(TelegramNetworkError):
        _run(make_request, monkeypatch)
    assert len(calls) == RETRIES


def test_telegram_refusals_are_not_retried(monkeypatch) -> None:
    """Отказ по существу повторять бессмысленно: ответ будет тем же."""
    calls = []

    async def make_request(bot, method):
        calls.append(1)
        raise TelegramBadRequest(method=None, message="chat not found")

    with pytest.raises(TelegramBadRequest):
        _run(make_request, monkeypatch)
    assert len(calls) == 1
