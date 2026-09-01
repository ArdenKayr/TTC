"""Кнопка на карточке-заявке должна отзываться сразу.

Из журнала ошибок на бою, записи №3–5 от 28.08.2026:

    ⚠ Регистрация: одобрение: Не удалось создать инвайт-ссылку
    TelegramBadRequest: query is too old and response timeout expired
    TelegramBadRequest: query is too old and response timeout expired

Админ нажал «Принять». Бот пошёл в Telegram за инвайт-ссылкой, связь в тот
момент подтормаживала — и пока он ждал, нажатие протухло: Telegram отводит
на ответ несколько секунд. Заявку бот всё-таки одобрил, а вот сказать об
этом уже не смог. Админ увидел зависшую кнопку, нажал второй раз — и второе
нажатие закончилось той же ошибкой.

Причина не в связи, а в порядке действий: бот отвечал на нажатие последним,
после всей работы. Здесь проверяется новый порядок — подтверждение первым
делом, работа потом, итог в самой карточке.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError

from bot import texts
from bot.keyboards.callback_data import RegReviewCB
from bot.routers.admin import registration_review


class _Card:
    """Карточка заявки в админ-чате."""

    def __init__(self, log: list[str]) -> None:
        self.log = log
        self.html_text = "Заявка на вступление"
        self.edited: str | None = None
        self.markup: object = "кнопки на месте"
        self.replies: list[str] = []

    async def edit_text(self, text: str, reply_markup=None) -> None:
        self.log.append("итог в карточке")
        self.edited = text
        self.markup = reply_markup

    async def reply(self, text: str) -> None:
        self.log.append("ответ на карточку")
        self.replies.append(text)


class _Callback:
    """Нажатие кнопки. Запоминает, в каком порядке бот к нему обращался."""

    def __init__(self, log: list[str], answer_error: Exception | None = None) -> None:
        self.log = log
        self.answer_error = answer_error
        self.message = _Card(log)
        self.bot = None

    async def answer(self, text: str | None = None, show_alert: bool = False) -> None:
        self.log.append("подтверждение нажатия")
        if self.answer_error is not None:
            raise self.answer_error


def _approve(monkeypatch, log: list[str], ok: bool, note: str, answer_error=None):
    """Прогоняет одобрение заявки и возвращает нажатие вместе с журналом."""

    async def fake_approve(session, bot, request_id, admin):
        log.append("разбор заявки")
        return ok, note

    monkeypatch.setattr(registration_review.registration_service, "approve", fake_approve)
    callback = _Callback(log, answer_error)
    asyncio.run(
        registration_review.cb_approve(
            callback,
            RegReviewCB(action="approve", request_id=str(uuid.uuid4())),
            session=object(),
            db_user=object(),
        )
    )
    return callback


def test_click_is_confirmed_before_the_work(monkeypatch) -> None:
    """Сначала подтверждение, потом работа — иначе нажатие протухнет."""
    log: list[str] = []
    _approve(monkeypatch, log, ok=True, note="✅ Принята")
    assert log == ["подтверждение нажатия", "разбор заявки", "итог в карточке"], (
        "Подтверждение нажатия должно быть первым действием: пока бот ходит "
        "за инвайт-ссылкой, Telegram успевает признать нажатие протухшим."
    )


@pytest.mark.parametrize(
    "error",
    [
        TelegramBadRequest(method=None, message="query is too old"),
        TelegramNetworkError(method=None, message="Request timeout error"),
    ],
    ids=["нажатие протухло", "связь не дошла"],
)
def test_broken_confirmation_does_not_cancel_the_review(monkeypatch, error) -> None:
    """Подтверждение — косметика. Его потеря не повод бросать заявку.

    Человек по ту сторону ждёт решения: оно важнее, чем «часики» на кнопке.
    """
    log: list[str] = []
    callback = _approve(monkeypatch, log, ok=True, note="✅ Принята", answer_error=error)
    assert log == ["подтверждение нажатия", "разбор заявки", "итог в карточке"]
    assert callback.message.edited is not None, "Итог разбора должен дойти до карточки."


def test_result_lands_in_the_card_and_removes_buttons(monkeypatch) -> None:
    """Итог виден всем админам и не исчезает через пару секунд."""
    log: list[str] = []
    callback = _approve(monkeypatch, log, ok=True, note="✅ Принята — Черешня")
    assert callback.message.edited == "Заявка на вступление\n\n✅ Принята — Черешня"
    assert callback.message.markup is None, (
        "После решения кнопки надо убрать — иначе по ним нажмут ещё раз."
    )


def test_failed_review_answers_without_touching_the_card(monkeypatch) -> None:
    """Заявку разобрал другой админ — в карточке уже его итог, портить нельзя."""
    log: list[str] = []
    callback = _approve(
        monkeypatch, log, ok=False, note=texts.REVIEW_ALREADY_PROCESSED
    )
    assert callback.message.edited is None, "Чужой итог в карточке затирать нельзя."
    assert callback.message.replies == [texts.REVIEW_ALREADY_PROCESSED], (
        "Админ должен понять, почему карточка не изменилась."
    )
