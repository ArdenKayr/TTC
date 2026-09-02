"""Создателя группы Telegram не исключает никому — это не сбой бота.

Из журнала ошибок на бою, запись №6 от 01.09.2026:

    ⚠ Бан: Роль сменена на «забанен», но исключить из группы не удалось:
    Bad Request: can't remove chat owner

Забанили аккаунт, который создал саму группу. Telegram отказал — и правильно
сделал: создателя группы не выгонит ни бот, ни человек, никакими правами.
Владельцу же прилетела карточка, неотличимая от настоящей поломки: «не
удалось», проверьте права бота. Чинить там нечего, а тревога настоящая.

Здесь проверяется, что бот различает два вида отказа: правило Telegram
объясняется словами, а поломка по-прежнему называется поломкой и приносит
её причину.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError

from bot.enums import UserRole
from bot.services import group_service, role_service

DONE = "В боте человек заблокирован"


def test_chat_owner_refusal_is_explained_not_alarmed() -> None:
    """Отказ по правилу Telegram читается как объяснение, а не как поломка."""
    note = group_service.describe_removal_failure(
        TelegramBadRequest(method=None, message="Bad Request: can't remove chat owner"), DONE
    )
    assert "создател" in note.lower(), "Должно быть сказано, что человек — создатель группы."
    assert "не удалось" not in note.lower(), (
        "«Не удалось» зовёт владельца чинить то, чего чинить нельзя."
    )
    assert DONE in note, "Из записи должно быть видно и то, что бот всё-таки сделал."


@pytest.mark.parametrize(
    "error",
    [
        TelegramBadRequest(method=None, message="Bad Request: not enough rights"),
        TelegramNetworkError(method=None, message="Request timeout error"),
    ],
    ids=["нет прав", "связь не дошла"],
)
def test_real_failure_still_names_its_reason(error) -> None:
    """Настоящая поломка остаётся поломкой — с причиной, по которой её искать."""
    note = group_service.describe_removal_failure(error, DONE)
    assert "не удалось" in note.lower()
    assert str(error) in note, "Без причины запись бесполезна: непонятно, что чинить."


def _ban(monkeypatch, error: Exception) -> str:
    """Банит человека при отказе Telegram и возвращает запись для владельца."""
    recorded: list[str] = []

    async def fake_report_issue(bot, *, source, note, tg_id=None, **kwargs):
        recorded.append(note)

    async def fake_add(*args, **kwargs):
        return None

    async def fake_dm(*args, **kwargs):
        return None

    class _Bot:
        async def ban_chat_member(self, chat_id, tg_id):
            raise error

    monkeypatch.setattr(role_service.settings, "group_chat_id", -1004358911617)
    monkeypatch.setattr(role_service.error_service, "report_issue", fake_report_issue)
    monkeypatch.setattr(role_service.audit_repo, "add", fake_add)
    monkeypatch.setattr(role_service.scenario_service, "dm", fake_dm)

    session = SimpleNamespace(commit=fake_add)
    actor = SimpleNamespace(tg_id=1, current_role=UserRole.OWNER)
    target = SimpleNamespace(
        tg_id=2,
        current_role=UserRole.USER,
        role_before_ban=None,
        banned_at=None,
        banned_reason=None,
    )
    asyncio.run(role_service.ban_user(session, _Bot(), actor, target, reason=None))
    assert target.current_role == UserRole.BANNED, "В боте бан должен сработать в любом случае."
    assert len(recorded) == 1, "Владелец должен узнать, что человек остался в группе."
    return recorded[0]


def test_ban_of_chat_owner_reports_the_rule(monkeypatch) -> None:
    """Бан создателя группы: в боте забанен, из группы не выйдет — и это нормально."""
    note = _ban(
        monkeypatch, TelegramBadRequest(method=None, message="Bad Request: can't remove chat owner")
    )
    assert "создател" in note.lower()
    assert "делать ничего не нужно" in note.lower()


def test_ban_with_broken_rights_still_alarms(monkeypatch) -> None:
    """А вот отобранные права — настоящая поломка, о ней надо тревожить."""
    note = _ban(monkeypatch, TelegramBadRequest(method=None, message="not enough rights"))
    assert "не удалось" in note.lower()
    assert "not enough rights" in note
