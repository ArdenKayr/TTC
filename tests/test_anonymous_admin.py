"""Админ, пишущий от лица группы, — всё ещё админ.

Из жизни (02.09.2026): владелец пересоздал группу, написал объявление в тему
«Объявления» от лица самой группы — и бот стёр его сообщение. Со стороны это
выглядело поломкой, а было честной работой охраны тем: Telegram в анонимных
сообщениях прячет автора за служебным аккаунтом, бот не нашёл его в своей
базе и принял за постороннего.

Отличить анонимного админа можно только по `sender_chat`. Писать от лица
группы Telegram разрешает исключительно её администраторам — значит этого
признака достаточно. А вот сообщение от имени чужого канала таким признаком
не является: его может отправить кто угодно, и в read-only теме ему не место.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from bot.enums import UserRole
from bot.routers.group import topic_guards

GROUP = -1004358911617
ANNOUNCEMENTS = 4
AFISHA = 7
FLOOD = 11


class _Message:
    """Сообщение в группе. Помнит, удалили его или нет."""

    def __init__(self, thread: int, sender_chat_id: int | None = None, text: str = "Объявление") -> None:
        self.chat = SimpleNamespace(id=GROUP, type="supergroup")
        self.message_thread_id = thread
        self.sender_chat = SimpleNamespace(id=sender_chat_id) if sender_chat_id else None
        self.text = text
        self.deleted = False

    async def delete(self) -> None:
        self.deleted = True


@pytest.fixture(autouse=True)
def _group_settings(monkeypatch):
    monkeypatch.setattr(topic_guards.settings, "group_chat_id", GROUP)
    monkeypatch.setattr(topic_guards.settings, "topic_announcements_id", ANNOUNCEMENTS)
    monkeypatch.setattr(topic_guards.settings, "topic_afisha_id", AFISHA)


def _handle(message: _Message, db_user=None) -> _Message:
    asyncio.run(topic_guards.group_message(message, db_user))
    return message


def _member(role: UserRole) -> SimpleNamespace:
    return SimpleNamespace(tg_id=1, current_role=role)


@pytest.mark.parametrize("thread", [ANNOUNCEMENTS, AFISHA], ids=["Объявления", "Афиша"])
def test_message_from_the_group_itself_survives(thread: int) -> None:
    """Ровно тот случай, из-за которого объявления владельца исчезали."""
    message = _handle(_Message(thread, sender_chat_id=GROUP))
    assert not message.deleted, (
        "От лица группы пишет её администратор — стирать такое нельзя."
    )


@pytest.mark.parametrize("thread", [ANNOUNCEMENTS, AFISHA], ids=["Объявления", "Афиша"])
def test_message_from_a_foreign_channel_is_deleted(thread: int) -> None:
    """От имени чужого канала может написать кто угодно — это не админ."""
    message = _handle(_Message(thread, sender_chat_id=-1009999999999))
    assert message.deleted


@pytest.mark.parametrize("thread", [ANNOUNCEMENTS, AFISHA], ids=["Объявления", "Афиша"])
def test_participant_is_still_deleted(thread: int) -> None:
    """Темы остаются только для чтения — ради этого охрана и существует."""
    message = _handle(_Message(thread), db_user=_member(UserRole.USER))
    assert message.deleted


@pytest.mark.parametrize(
    "role", [UserRole.ADMIN, UserRole.SUPERADMIN, UserRole.OWNER], ids=lambda r: r.value
)
def test_named_admins_still_write(role: UserRole) -> None:
    """Админ, пишущий под своим именем, как писал, так и пишет."""
    message = _handle(_Message(ANNOUNCEMENTS), db_user=_member(role))
    assert not message.deleted


def test_free_topics_are_not_guarded() -> None:
    """Во «Флуде» охраны нет — там общаются все."""
    message = _handle(_Message(FLOOD), db_user=_member(UserRole.USER))
    assert not message.deleted


def test_stranger_in_a_free_topic_is_left_alone() -> None:
    """Незнакомец в свободной теме — не повод удалять сообщение."""
    message = _handle(_Message(FLOOD))
    assert not message.deleted
