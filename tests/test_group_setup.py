"""Закрытая группа: как бот её находит и как сообщает, что не нашёл.

Группу сообщества сделали закрытой — войти в неё можно только по ссылке от
бота. У закрытой группы нет публичного имени, а искал бот её именно по имени:
в один день `@The_True_Course_SPB` перестал открываться, и вместе с ним молча
выключились ссылки на вступление, Афиша и охрана тем. Заметили это по жалобам
людей, а не по журналу.

Здесь проверяется то, из-за чего поломка так долго оставалась незаметной:
номер группы теперь сверяется всегда, право приглашать — тоже, а сам номер
можно спросить у бота, раз спросить его больше не у кого.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramAPIError

from bot import main, texts
from bot.config import settings
from bot.db.models import User
from bot.enums import UserRole
from bot.routers.group import topic_guards


class _Chat:
    def __init__(self, chat_id: int) -> None:
        self.id = chat_id


class _Admin:
    """Бот-администратор: право приглашать у него либо есть, либо нет."""

    status = "administrator"

    def __init__(self, can_invite_users: bool) -> None:
        self.can_invite_users = can_invite_users


class _Plain:
    """Бота просто добавили в группу: поля can_invite_users у такого нет вовсе."""

    status = "member"


class _Bot:
    def __init__(self, chat_id: int = -1002222, member=None, opens: bool = True) -> None:
        self.chat_id = chat_id
        self.member = _Admin(True) if member is None else member
        self.opens = opens
        self.asked: list = []

    async def get_chat(self, chat):
        self.asked.append(chat)
        if not self.opens:
            raise TelegramAPIError(method=None, message="chat not found")
        return _Chat(self.chat_id)

    async def me(self):
        return SimpleNamespace(id=777)

    async def get_chat_member(self, chat_id, user_id):
        return self.member


@pytest.fixture
def configured(monkeypatch):
    """Задаёт GROUP_CHAT_ID и возвращает функцию «запустить проверку»."""

    def run(value, bot: _Bot) -> None:
        monkeypatch.setattr(settings, "group_chat_id", value, raising=False)
        asyncio.run(main.resolve_group_chat_id(bot))

    return run


# --- Как бот находит группу --------------------------------------------------


def test_a_public_name_still_becomes_a_number(configured) -> None:
    """Имя поддерживается по-прежнему: у других чатов оно может и остаться."""
    bot = _Bot(chat_id=-1002222)
    configured("@some_public_group", bot)

    assert settings.group_chat_id == -1002222


def test_a_number_is_checked_too(configured) -> None:
    """Раньше число принималось на веру — ошибка в нём не оставляла следов."""
    bot = _Bot(chat_id=-1002222)
    configured(-1002222, bot)

    assert bot.asked == [-1002222]
    assert settings.group_chat_id == -1002222


def test_a_name_that_does_not_open_switches_the_group_off(configured) -> None:
    """Имя, которое не открылось, слать некуда — так было и с закрытой группой."""
    configured("@gone", _Bot(opens=False))

    assert settings.group_chat_id is None


def test_a_number_that_does_not_open_is_kept(configured) -> None:
    """Число задано человеком явно: разовый сбой связи не выключает группу до
    следующего перезапуска, иначе одна неудачная минута стоила бы суток."""
    configured(-1002222, _Bot(opens=False))

    assert settings.group_chat_id == -1002222


def test_a_failure_is_written_down(configured, caplog) -> None:
    caplog.set_level(logging.WARNING)
    configured("@gone", _Bot(opens=False))

    assert "@gone" in caplog.text


def test_an_unset_group_says_so(configured, caplog) -> None:
    caplog.set_level(logging.WARNING)
    configured(None, _Bot())

    assert "GROUP_CHAT_ID" in caplog.text


# --- Может ли бот вообще впустить человека -----------------------------------


def test_a_missing_invite_right_is_shouted_about(configured, caplog) -> None:
    """Без этого права закрытая группа заперта наглухо: другой двери нет."""
    caplog.set_level(logging.WARNING)
    configured(-1002222, _Bot(member=_Admin(False)))

    assert "приглашать" in caplog.text


def test_a_bot_that_is_not_an_admin_is_shouted_about(configured, caplog) -> None:
    caplog.set_level(logging.WARNING)
    configured(-1002222, _Bot(member=_Plain()))

    assert "приглашать" in caplog.text


def test_a_proper_setup_is_quiet(configured, caplog) -> None:
    caplog.set_level(logging.WARNING)
    configured(-1002222, _Bot(member=_Admin(True)))

    assert caplog.text == ""


# --- Откуда взять номер закрытой группы --------------------------------------


class _Message:
    def __init__(self, chat_id: int, thread_id: int | None = None) -> None:
        self.chat = SimpleNamespace(id=chat_id, type="supergroup")
        self.message_thread_id = thread_id
        self.replies: list[str] = []

    async def reply(self, text: str) -> None:
        self.replies.append(text)


def _person(role: UserRole) -> User:
    return User(
        tg_id=5,
        display_name="Кто-то",
        birth_date=date(2000, 1, 1),
        current_role=role,
    )


def test_an_admin_is_told_the_chat_and_topic_number() -> None:
    message = _Message(-1002222, thread_id=17)
    asyncio.run(topic_guards.cmd_chat_id(message, _person(UserRole.ADMIN)))

    (answer,) = message.replies
    assert "-1002222" in answer
    assert "17" in answer


def test_outside_a_topic_only_the_chat_number_is_named() -> None:
    message = _Message(-1002222)
    asyncio.run(topic_guards.cmd_chat_id(message, _person(UserRole.ADMIN)))

    (answer,) = message.replies
    assert "-1002222" in answer
    assert texts.CHAT_ID_TOPIC.strip() not in answer


def test_the_number_is_named_even_in_an_unconfigured_group(monkeypatch) -> None:
    """Ради этого случая команда и сделана: группы в настройках ещё нет."""
    monkeypatch.setattr(settings, "group_chat_id", None, raising=False)
    message = _Message(-1002222)
    asyncio.run(topic_guards.cmd_chat_id(message, _person(UserRole.OWNER)))

    assert message.replies


@pytest.mark.parametrize("role", [UserRole.USER, UserRole.ORGANIZER])
def test_participants_get_no_answer(role: UserRole) -> None:
    """Иначе в общем чате начнётся перекличка служебными номерами."""
    message = _Message(-1002222)
    asyncio.run(topic_guards.cmd_chat_id(message, _person(role)))

    assert message.replies == []


def test_a_stranger_gets_no_answer() -> None:
    message = _Message(-1002222)
    asyncio.run(topic_guards.cmd_chat_id(message, None))

    assert message.replies == []
