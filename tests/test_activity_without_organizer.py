"""Мероприятие, у которого не осталось организатора.

Удалить можно любую запись, и ссылки на удалённого человека обнуляются
(с миграции 0011). Мероприятие при этом остаётся: организатора нет, а карточка
в Афише висит. Когда такое мероприятие закрывают, бот раньше вёл себя дважды
неправильно — оба случая всплыли из ошибки №2 на бою:

* писал владельцу «организатору не доставилось уведомление», хотя писать было
  некому (это проверяется в test_delivery_outcome.py);
* не трогал карточку в Афише — и закрытое мероприятие продолжало выглядеть
  активным для всех участников.

Здесь — про второе.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date

import pytest

from bot import texts
from bot.db.models import Activity, User
from bot.enums import ActivityStatus, UserRole
from bot.services import activity_service


@pytest.fixture
def owner() -> User:
    return User(
        tg_id=1,
        display_name="Владелец",
        birth_date=date(2000, 1, 1),
        current_role=UserRole.OWNER,
    )


class _Session:
    """Отдаёт мероприятие и делает вид, что организатора в базе нет."""

    def __init__(self, activity: Activity) -> None:
        self.activity = activity

    async def get(self, model, key):
        return self.activity if model is Activity else None

    async def scalar(self, *args, **kwargs):
        return 0

    async def commit(self):
        pass


def _activity(**kwargs) -> Activity:
    return Activity(
        activity_id=uuid.uuid4(),
        title="Мероприятие без организатора",
        description="Осталось от удалённого человека",
        status=ActivityStatus.ACTIVE,
        afisha_message_id=555,
        organizer_id=None,
        **kwargs,
    )


@pytest.fixture
def edits(monkeypatch):
    """Записывает правки карточки в Афише и обращения к владельцу."""
    log = {"cards": [], "captions": [], "issues": [], "dm": []}

    async def fake_edit(bot, message_id, text, is_caption=False):
        log["cards"].append((message_id, text))
        log["captions"].append(is_caption)
        return True

    async def fake_dm(bot, session, tg_id, key, **kwargs):
        log["dm"].append((tg_id, key))
        return activity_service.scenario_service.Delivery.NO_ADDRESSEE

    async def fake_issue(bot, **kwargs):
        log["issues"].append(kwargs)

    async def fake_audit(*args, **kwargs):
        pass

    monkeypatch.setattr(activity_service.notification_service, "edit_afisha_card", fake_edit)
    monkeypatch.setattr(activity_service.scenario_service, "dm", fake_dm)
    monkeypatch.setattr(activity_service.error_service, "report_issue", fake_issue)
    monkeypatch.setattr(activity_service.audit_repo, "add", fake_audit)
    return log


def _close(activity, admin, *, cancelled=False):
    return asyncio.run(
        activity_service.finish_activity(
            _Session(activity), None, activity.activity_id, admin, cancelled
        )
    )


def test_afisha_card_is_marked_closed_without_organizer(edits, owner):
    """Главное: в Афише не должно остаться «активного» закрытого мероприятия."""
    activity = _activity()
    ok, _ = _close(activity, owner)

    assert ok
    assert activity.status == ActivityStatus.COMPLETED
    (message_id, text), = edits["cards"]
    assert message_id == 555
    assert texts.AFISHA_DONE_LINE.strip() in text
    assert texts.USER_DELETED_LABEL in text


def test_cancelled_card_says_cancelled(edits, owner):
    activity = _activity()
    _close(activity, owner, cancelled=True)

    (_, text), = edits["cards"]
    assert texts.AFISHA_CANCELLED_LINE.strip() in text


def test_owner_is_not_bothered_about_a_deleted_organizer(edits, owner):
    """Некому писать — не о чем и сообщать."""
    _close(_activity(), owner)
    assert edits["issues"] == []


def test_a_card_with_a_picture_is_marked_in_its_caption(edits, owner):
    """Пост с картинкой — это подпись, а не текст: правится другим способом.

    Перепутать способы — значит получить отказ Telegram и закрытое
    мероприятие, которое так и висит в Афише активным.
    """
    _close(_activity(afisha_is_caption=True), owner)
    assert edits["captions"] == [True]


def test_an_old_text_card_is_still_marked_as_text(edits, owner):
    """У мероприятий, поданных до картинок, карточка обычная текстовая.

    Проверяем именно выбранный способ правки, а не значение поля: у записи,
    не прошедшей через базу, умолчание ещё не проставлено и там пусто — на
    поведение это не влияет, но букву сравнивать бессмысленно.
    """
    _close(_activity(), owner)
    assert not edits["captions"][0]
