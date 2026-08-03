"""«Не смогли отправить» и «отправлять некому» — разные вещи.

Из журнала ошибок на бою, запись №2 от 2026-08-02:

    ⚠ Мероприятие: завершение/отмена: Мероприятие «охаедатебае» закрыто,
    но организатору не доставилось уведомление.

Организатора у того мероприятия не было вовсе: человека удалили из базы, и
ссылка на него обнулилась (так работает удаление записей с миграции 0011).
Писать было некому — а владельцу прилетела карточка ошибки, будто сообщение
потерялось по дороге. Это ложная тревога: чем больше таких, тем меньше
внимания настоящим.

Здесь проверяется, что оба случая различаются и что тревожит владельца только
настоящая неудача отправки.
"""

from __future__ import annotations

import asyncio

from bot.services.scenario_service import Delivery, dm


class _FailingBot:
    """Телеграм отвечает отказом — человек не запускал бота или заблокировал."""

    async def send_message(self, *args, **kwargs):
        from aiogram.exceptions import TelegramForbiddenError

        raise TelegramForbiddenError(method=None, message="bot was blocked by the user")


class _SilentBot:
    def __init__(self) -> None:
        self.sent: list[tuple] = []

    async def send_message(self, tg_id, text, **kwargs):
        self.sent.append((tg_id, text))


class _Session:
    """Сценарий никто не переопределял — берётся текст по умолчанию."""

    async def scalar(self, *args, **kwargs):
        return None

    async def execute(self, *args, **kwargs):
        raise AssertionError("шаблон читается через content_repo, а не напрямую")


def _dm(bot, tg_id, monkeypatch):
    async def fake_get(session, key):
        return None

    from bot.services import scenario_service

    monkeypatch.setattr(scenario_service.content_repo, "get", fake_get)
    return asyncio.run(dm(bot, _Session(), tg_id, "org_demoted"))


def test_no_addressee_is_not_a_failure(monkeypatch):
    """Организатора удалили — писать некому, и это не сбой."""
    result = _dm(_SilentBot(), None, monkeypatch)
    assert result is Delivery.NO_ADDRESSEE
    assert not result.is_problem


def test_blocked_bot_is_a_failure(monkeypatch):
    """А вот это владельцу знать нужно: человек есть, сообщение не дошло."""
    result = _dm(_FailingBot(), 42, monkeypatch)
    assert result is Delivery.FAILED
    assert result.is_problem


def test_successful_send(monkeypatch):
    bot = _SilentBot()
    result = _dm(bot, 42, monkeypatch)
    assert result is Delivery.SENT
    assert not result.is_problem
    assert bot.sent and bot.sent[0][0] == 42


def test_only_sent_counts_as_delivered():
    """`if delivered:` должно означать «человек получил», а не «обошлось»."""
    assert bool(Delivery.SENT)
    assert not bool(Delivery.FAILED)
    assert not bool(Delivery.NO_ADDRESSEE)
