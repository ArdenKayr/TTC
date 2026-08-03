"""Смена роли обязана дойти до самого человека.

Нижнее меню в Telegram живёт, пока его не заменят новым сообщением. Раньше
set_role менял роль только в базе — и человек, назначенный суперадмином,
оставался со старой клавиатурой (в худшем случае — с кнопками «Регистрация»
и «Кто мы?», если он не писал боту с момента одобрения анкеты). Хуже того,
нигде не оставалось следа: роль сменилась, а меню — нет.
"""

import asyncio
from datetime import date
from types import SimpleNamespace

import pytest

from bot import texts
from bot.db.models import User
from bot.enums import UserRole
from bot.services import role_service
from bot.services.scenario_service import Delivery


def _user(tg_id: int, role: UserRole) -> User:
    return User(
        tg_id=tg_id,
        display_name=f"Тест-{tg_id}",
        birth_date=date(2000, 1, 1),
        current_role=role,
    )


class _Session:
    async def commit(self) -> None:
        pass


@pytest.fixture
def calls(monkeypatch):
    """Подменяет всё, что ходит наружу, и записывает вызовы."""
    log = SimpleNamespace(dm=[], issues=[], delivered=Delivery.SENT)

    async def fake_add(*args, **kwargs):
        pass

    async def fake_dm(bot, session, tg_id, key, **kwargs):
        log.dm.append({"tg_id": tg_id, "key": key, **kwargs})
        return log.delivered

    async def fake_report_issue(bot, **kwargs):
        log.issues.append(kwargs)

    monkeypatch.setattr(role_service.audit_repo, "add", fake_add)
    monkeypatch.setattr(role_service.scenario_service, "dm", fake_dm)
    monkeypatch.setattr(role_service.error_service, "report_issue", fake_report_issue)
    return log


def _promote(target_role=UserRole.USER, new_role=UserRole.SUPERADMIN):
    owner = _user(1, UserRole.OWNER)
    target = _user(2, target_role)
    result = asyncio.run(
        role_service.set_role(_Session(), None, owner, target, new_role)
    )
    return result, target


def test_new_superadmin_gets_message_with_updated_menu(calls):
    result, target = _promote()

    assert result.error is None
    assert result.notified is True
    assert target.current_role == UserRole.SUPERADMIN

    (sent,) = calls.dm
    assert sent["tg_id"] == 2
    assert sent["key"] == "role_changed"
    assert sent["role"] == texts.ROLE_LABELS[UserRole.SUPERADMIN]

    labels = {b.text for row in sent["reply_markup"].keyboard for b in row}
    assert texts.BTN.ADMIN_MODE in labels
    assert texts.BTN.START_REGISTER not in labels


def test_demotion_takes_admin_button_away(calls):
    _promote(target_role=UserRole.SUPERADMIN, new_role=UserRole.USER)

    (sent,) = calls.dm
    labels = {b.text for row in sent["reply_markup"].keyboard for b in row}
    assert texts.BTN.ADMIN_MODE not in labels


def test_undelivered_notice_lands_in_logs(calls):
    """Человек не запускал бота — операция успешна, но след обязан остаться."""
    calls.delivered = Delivery.FAILED
    result, _ = _promote()

    assert result.error is None
    assert result.notified is False
    (issue,) = calls.issues
    assert issue["tg_id"] == 2
    assert issue["source"] == "Смена роли"
    assert "меню" in issue["note"]


def test_rejected_change_notifies_nobody(calls):
    """Суперадмин не трогает суперадмина — ни сообщения, ни записи в логах."""
    actor = _user(1, UserRole.SUPERADMIN)
    target = _user(2, UserRole.SUPERADMIN)
    result = asyncio.run(
        role_service.set_role(_Session(), None, actor, target, UserRole.USER)
    )

    assert result.error == texts.ROLE_TARGET_PROTECTED
    assert calls.dm == []
    assert calls.issues == []
