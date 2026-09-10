"""Автоприём: кого бот пускает сам и кого не пускает никогда.

Появился из расчёта на тысячу человек (09.09.2026): железо и Telegram выдержат,
а руки — нет. Тысяча заявок по пятнадцать секунд на каждую это часы нажатий,
и очередь встанет на этом месте, сколько её ни ускоряй. Поэтому поток надо
сокращать: заявки, в которых нечего решать, бот принимает сам.

Здесь проверяется не «хороший ли человек» — этого код знать не может, — а что
правила отсекают ровно то, что должны, и что решение никогда не проходит мимо
админов молча. Каждое правило проверяется отдельно: правило, которое перестало
работать, не должно прятаться за соседним.
"""

from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace

import pytest

from bot import texts
from bot.services import autoapprove_service, registration_service

TODAY = date(2026, 9, 10)


def _request(**changes):
    """Заявка, которая проходит автоприём. Тест ломает в ней ровно одно поле."""
    fields = {
        "university_request_id": None,
        "university_id": 7,
        "university_group": "ИКНТ-32",
        "attempt_number": 1,
        "full_name": "Аня",
        "birth_date": date(2005, 3, 14),  # 21 год на TODAY
    }
    fields.update(changes)
    return SimpleNamespace(**fields)


# --- Правила ---


def test_ordinary_application_passes() -> None:
    """Обычная студенческая заявка проходит: решать в ней нечего."""
    assert autoapprove_service.check(_request(), TODAY).ok is True


@pytest.mark.parametrize(
    "changes, expected_in_reason",
    [
        ({"university_request_id": "есть"}, "новый вуз"),
        ({"university_id": None}, "справочник"),
        ({"university_group": None}, "групп"),
        ({"university_group": ""}, "групп"),
        ({"attempt_number": 2}, "повторная"),
        ({"full_name": "Аня t.me/kanal"}, "имени"),
        ({"full_name": "Аня @kanal"}, "имени"),
        ({"full_name": "Аня https://spam.ru"}, "имени"),
        ({"full_name": "Аня www.spam.ru"}, "имени"),
        ({"birth_date": date(2015, 3, 14)}, "возраст"),
        ({"birth_date": date(1970, 3, 14)}, "возраст"),
    ],
    ids=[
        "заявка на новый вуз",
        "вуз не из справочника",
        "нет учебной группы",
        "пустая учебная группа",
        "повторная заявка",
        "ссылка t.me в имени",
        "упоминание в имени",
        "ссылка http в имени",
        "ссылка www в имени",
        "слишком юный",
        "слишком взрослый",
    ],
)
def test_each_rule_stops_the_application(changes: dict, expected_in_reason: str) -> None:
    """Каждое правило работает само по себе и объясняет свой отказ."""
    verdict = autoapprove_service.check(_request(**changes), TODAY)
    assert verdict.ok is False
    assert expected_in_reason in verdict.reason.lower(), (
        f"Причина «{verdict.reason}» не объясняет админу, почему заявка ждёт его."
    )


def test_new_university_is_never_auto_approved() -> None:
    """Заявку с новым вузом не пропустит даже безупречная во всём остальном.

    Иначе бот впустил бы человека с вузом, которого в справочнике нет, — а
    решение по вузу принимает админ, и оно может быть отказом.
    """
    verdict = autoapprove_service.check(_request(university_request_id="есть"), TODAY)
    assert verdict.ok is False


@pytest.mark.parametrize(
    "birth, ok",
    [
        (date(2010, 9, 10), True),  # 16 исполнилось сегодня — проходит
        (date(2010, 9, 11), False),  # 16 будет только завтра — пока нет
        (date(1991, 9, 9), True),  # 35 исполнилось вчера — граница включительно
        (date(1990, 9, 10), False),  # 36 — уже вне обычного
    ],
    ids=["16 сегодня", "16 завтра", "35 и один день", "36 лет"],
)
def test_age_boundaries(birth: date, ok: bool) -> None:
    """Границы возраста считаются по дню рождения, а не по году."""
    assert autoapprove_service.check(_request(birth_date=birth), TODAY).ok is ok


def test_age_is_counted_in_full_years() -> None:
    assert autoapprove_service.age_on(date(2005, 3, 14), TODAY) == 21
    assert autoapprove_service.age_on(date(2005, 12, 31), TODAY) == 20


# --- Как решение доходит до админов ---


class _Sent:
    """Что ушло в админ-чат."""

    def __init__(self) -> None:
        self.cards: list[tuple[str, object]] = []


def _run_decide(monkeypatch, *, auto_on: bool, request=None, approve_ok: bool = True) -> _Sent:
    sent = _Sent()
    approved: list[bool] = []

    async def fake_render(session, req, university_line=None):
        return "КАРТОЧКА"

    async def fake_send(bot, text, keyboard=None, photo_file_id=None, **kwargs):
        sent.cards.append((text, keyboard))
        return True

    async def fake_is_on(session, key):
        return auto_on

    async def fake_approve(session, bot, request_id, admin):
        approved.append(admin is None)
        return approve_ok, "✅ Принята автоматически"

    monkeypatch.setattr(registration_service, "render_registration_card", fake_render)
    monkeypatch.setattr(
        registration_service.notification_service, "send_admin_card", fake_send
    )
    monkeypatch.setattr(registration_service.settings_service, "is_on", fake_is_on)
    monkeypatch.setattr(registration_service, "approve", fake_approve)

    req = request if request is not None else _request()
    req.request_id = "id"
    req.tg_id = 1419203590
    sent.auto = asyncio.run(registration_service.decide_or_ask(None, None, req))
    sent.approved_by_bot = approved
    return sent


def test_switch_off_changes_nothing(monkeypatch) -> None:
    """Автоприём выключен — всё как было: карточка с кнопками, решает человек."""
    sent = _run_decide(monkeypatch, auto_on=False)
    assert sent.auto is False
    assert sent.approved_by_bot == [], "Выключенный автоприём не имеет права никого принять."
    text, keyboard = sent.cards[0]
    assert text == "КАРТОЧКА"
    assert keyboard is not None, "Без кнопок админу нечем разобрать заявку."


def test_approved_application_still_reaches_admins(monkeypatch) -> None:
    """Принятая ботом заявка всё равно видна админам — с пометкой и без кнопок.

    Это главное свойство автоприёма: он убирает ожидание, а не надзор.
    Посмотреть, кого впустили, можно в любой момент.
    """
    sent = _run_decide(monkeypatch, auto_on=True)
    assert sent.auto is True
    assert sent.approved_by_bot == [True], "Принимать должен бот, без имени админа."
    text, keyboard = sent.cards[0]
    assert "Принята автоматически" in text
    assert keyboard is None, "Кнопки под уже решённой заявкой только сбивают с толку."


def test_rejected_by_rules_says_why(monkeypatch) -> None:
    """Заявка, не прошедшая правила, уходит админам с причиной и с кнопками."""
    sent = _run_decide(monkeypatch, auto_on=True, request=_request(attempt_number=3))
    assert sent.auto is False
    assert sent.approved_by_bot == []
    text, keyboard = sent.cards[0]
    assert "повторная" in text.lower(), "Админ должен видеть, почему заявка досталась ему."
    assert keyboard is not None


def test_failed_auto_approval_returns_the_decision_to_people(monkeypatch) -> None:
    """Автоприём не сработал технически — решение возвращается людям.

    Заявку мог успеть разобрать админ или её вовсе нет. Оставить её без
    кнопок значило бы потерять: в очереди её тоже не будет.
    """
    sent = _run_decide(monkeypatch, auto_on=True, approve_ok=False)
    assert sent.auto is False
    text, keyboard = sent.cards[-1]
    assert keyboard is not None, "Кнопки обязаны вернуться, иначе заявку некому разобрать."
    assert "Принята автоматически" not in text


def test_rules_are_not_configurable_by_accident() -> None:
    """Правила живут в коде, а не в настройках, — и это записано числом.

    Набор галочек в панели выглядел бы гибкостью, а означал бы, что в любой
    момент неизвестно, по каким правилам бот кого-то впустил.
    """
    assert autoapprove_service.AGE_MIN == 16
    assert autoapprove_service.AGE_MAX == 35
    assert texts.AUTO_PANEL.count("•") == 5, (
        "В панели перечислены все правила: список в тексте и код должны совпадать."
    )
