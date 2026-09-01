"""Как бот дозванивается до Telegram: протокол, ожидание, повторы.

С боевого сервера api.telegram.org доступен по IPv6 и **недоступен по
обычному IPv4**: соединение не устанавливается вовсе и молча висит. По
умолчанию библиотека ждёт минуту — и всё это время человек по ту сторону
смотрит на молчащего бота, обычно нажимая кнопку ещё раз.

Замеры из контейнера 02.09.2026: IPv6 — соединение за 0,04 с (4 попытки из
4), IPv4 — таймаут (4 из 4, ни одного успеха). За неделю в журнале около 70
строк про такие таймауты, и каждая — чьё-то потерянное действие.

Отсюда три меры:

* можно запретить IPv4 совсем (`TELEGRAM_IP_FAMILY=ipv6` в настройках) —
  тогда вместо минутного ожидания мёртвого маршрута сразу будет отказ;
* ожидание ограничено: пять секунд на то, чтобы соединиться, и двадцать
  на весь запрос вместо шестидесяти;
* короткие провалы связи бот переживает сам — повторяет запрос, но только
  если до Telegram он даже не дозвонился.

Опрос новых событий под эти правила не попадает: у него свой, намеренно
долгий таймаут — так устроен long polling, и укорачивать его нельзя.
"""

import asyncio
import logging
import socket
import time

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.session.middlewares.base import NextRequestMiddlewareType
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import Response, TelegramMethod
from aiogram.methods.base import TelegramType
from aiohttp import ClientTimeout

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT = 5.0  # сколько ждём установки соединения
TOTAL_TIMEOUT = 20.0  # сколько ждём весь запрос целиком
RETRIES = 3  # столько раз пробуем, если не дозвонились
RETRY_PAUSE = 1.0  # пауза между попытками

FAMILIES = {
    "auto": socket.AF_UNSPEC,  # как решит система: сначала IPv6, потом IPv4
    "ipv6": socket.AF_INET6,
    "ipv4": socket.AF_INET,
}


def looks_like_no_connection(elapsed: float) -> bool:
    """Похоже, что до Telegram не дозвонились вовсе?

    Различаем по времени, потому что библиотека называет обе беды одинаково.
    На соединение отведено `CONNECT_TIMEOUT`, на весь запрос — вчетверо
    больше. Уложились в первое — значит, запрос до Telegram не ушёл и
    повторить его безопасно. Ждали дольше — сообщение могло и дойти, просто
    ответ не вернулся: повтор тогда обернётся вторым сообщением человеку.
    """
    return elapsed < CONNECT_TIMEOUT + 1.0


async def retry_on_lost_connection(
    make_request: NextRequestMiddlewareType[TelegramType],
    bot: Bot,
    method: TelegramMethod[TelegramType],
) -> Response[TelegramType]:
    """Повторяет запрос, если связь пропала до того, как он ушёл.

    Провалы здесь короткие — секунды, — поэтому вторая попытка обычно
    проходит. Дублировать чужие сообщения при этом нельзя, отсюда и
    осторожность: повторяем только заведомо не дошедшее.
    """
    for attempt in range(1, RETRIES + 1):
        started = time.monotonic()
        try:
            return await make_request(bot, method)
        except TelegramNetworkError as error:
            elapsed = time.monotonic() - started
            if attempt == RETRIES or not looks_like_no_connection(elapsed):
                raise
            logger.warning(
                "Не дозвонились до Telegram (%s, попытка %d из %d, %.1f с): %s. Повторяю.",
                method.__api_method__,
                attempt,
                RETRIES,
                elapsed,
                error,
            )
            await asyncio.sleep(RETRY_PAUSE)
    raise AssertionError("сюда не попасть: последняя попытка либо вернёт ответ, либо бросит")


class TelegramSession(AiohttpSession):
    """Связь с Telegram с ограниченным ожиданием и выбором протокола."""

    def __init__(self, ip_family: str = "auto") -> None:
        super().__init__()
        family = FAMILIES.get(ip_family)
        if family is None:
            raise ValueError(
                f"TELEGRAM_IP_FAMILY={ip_family!r} — непонятное значение. "
                f"Допустимые: {', '.join(FAMILIES)}."
            )
        if family is not socket.AF_UNSPEC:
            self._connector_init["family"] = family
        # Значение уходит прямо в aiohttp, поэтому здесь можно задать
        # раздельные сроки: отдельно на соединение, отдельно на весь запрос.
        self.timeout = ClientTimeout(total=TOTAL_TIMEOUT, sock_connect=CONNECT_TIMEOUT)
        self.middleware(retry_on_lost_connection)
        logger.info(
            "Связь с Telegram: протокол %s, соединение до %.0f с, запрос до %.0f с, попыток %d.",
            ip_family,
            CONNECT_TIMEOUT,
            TOTAL_TIMEOUT,
            RETRIES,
        )
