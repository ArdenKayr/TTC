"""Новая ссылка на вступление в группу — в любой момент.

Жалоба живых людей: ссылка именная и живёт 15 минут, а её копируют, отвлекаются
и возвращаются, когда она уже истекла. Человек с одобренной заявкой оставался за
дверью и не понимал, что делать. Теперь дверь открывается заново одной кнопкой.

Здесь проверяется то, из-за чего кнопка может оказаться бесполезной: ссылка
должна создаваться теми же правилами, что и при одобрении (иначе они разъедутся),
а тому, кто уже в группе, второй ссылки не нужно.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from bot import texts
from bot.config import settings
from bot.keyboards.common_kb import info_menu_kb
from bot.services import registration_service


class _Link:
    def __init__(self, url: str) -> None:
        self.invite_link = url


class _Member:
    def __init__(self, status: str) -> None:
        self.status = status


class _Bot:
    """Подставной бот: запоминает, с чем звали, и отвечает заготовкой."""

    def __init__(self, member_status: str = "left") -> None:
        self.created: list[dict] = []
        self.member_status = member_status

    async def create_chat_invite_link(self, chat_id, **kwargs):
        self.created.append({"chat_id": chat_id, **kwargs})
        return _Link("https://t.me/+new")

    async def get_chat_member(self, chat_id, tg_id):
        return _Member(self.member_status)


@pytest.fixture
def issues(monkeypatch) -> list:
    """Перехватывает жалобы владельцу — сбой не должен теряться молча."""
    log: list = []

    async def fake_issue(bot, **kwargs):
        log.append(kwargs)

    monkeypatch.setattr(registration_service.error_service, "report_issue", fake_issue)
    monkeypatch.setattr(settings, "group_chat_id", -100500, raising=False)
    return log


# --- Как создаётся ссылка ----------------------------------------------------


def test_the_link_is_personal_and_short_lived(issues) -> None:
    """Одноразовая и именная — как при одобрении заявки: правила общие."""
    bot = _Bot()
    link = asyncio.run(registration_service.create_invite_link(bot, 42, "тест"))

    assert link == "https://t.me/+new"
    (call,) = bot.created
    assert call["member_limit"] == 1
    assert "42" in call["name"]
    assert issues == []


def test_the_link_expires_when_promised(issues) -> None:
    """Срок в тексте и срок у ссылки — одно и то же число."""
    bot = _Bot()
    asyncio.run(registration_service.create_invite_link(bot, 42, "тест"))

    (call,) = bot.created
    left = call["expire_date"] - datetime.now(timezone.utc)
    assert abs(left.total_seconds() - registration_service.INVITE_LINK_TTL.total_seconds()) < 5
    assert registration_service.INVITE_LINK_MINUTES == 15


def test_a_failure_is_not_swallowed(issues, monkeypatch) -> None:
    """Человек остался без ссылки — владелец должен об этом узнать."""
    from aiogram.exceptions import TelegramAPIError

    bot = _Bot()

    async def boom(*args, **kwargs):
        raise TelegramAPIError(method=None, message="not enough rights")

    monkeypatch.setattr(bot, "create_chat_invite_link", boom)
    assert asyncio.run(registration_service.create_invite_link(bot, 42, "тест")) is None
    assert len(issues) == 1


def test_an_unconfigured_group_is_reported_too(monkeypatch) -> None:
    log: list = []

    async def fake_issue(bot, **kwargs):
        log.append(kwargs)

    monkeypatch.setattr(registration_service.error_service, "report_issue", fake_issue)
    monkeypatch.setattr(settings, "group_chat_id", None, raising=False)

    assert asyncio.run(registration_service.create_invite_link(_Bot(), 42, "тест")) is None
    assert len(log) == 1


# --- Кому ссылка не нужна ----------------------------------------------------


@pytest.mark.parametrize("status", ["member", "administrator", "creator"])
def test_those_already_inside_are_told_so(issues, status: str) -> None:
    assert asyncio.run(registration_service.is_group_member(_Bot(status), 42))


@pytest.mark.parametrize("status", ["left", "kicked", "restricted"])
def test_those_outside_get_a_link(issues, status: str) -> None:
    assert not asyncio.run(registration_service.is_group_member(_Bot(status), 42))


def test_a_silent_telegram_does_not_lock_people_out(issues, monkeypatch) -> None:
    """Не ответил Telegram — выдаём ссылку: отказать тому, кто снаружи, хуже."""
    from aiogram.exceptions import TelegramAPIError

    bot = _Bot()

    async def boom(*args, **kwargs):
        raise TelegramAPIError(method=None, message="chat not found")

    monkeypatch.setattr(bot, "get_chat_member", boom)
    assert not asyncio.run(registration_service.is_group_member(bot, 42))


# --- Где человек эту кнопку найдёт -------------------------------------------


def test_the_button_lives_in_the_information_menu() -> None:
    labels = {
        button.text for row in info_menu_kb(False).keyboard for button in row
    }
    assert texts.BTN.INFO_GROUP_LINK in labels


def test_the_approval_message_says_where_to_get_a_new_one() -> None:
    """Иначе кнопку найдёт только тот, кто и так листает меню от скуки."""
    text = texts.APPROVED_DM_INVITE.format(
        link="https://t.me/+x",
        minutes=registration_service.INVITE_LINK_MINUTES,
        button=texts.BTN.INFO_GROUP_LINK,
    )
    assert texts.BTN.INFO_GROUP_LINK in text
    assert "15" in text
