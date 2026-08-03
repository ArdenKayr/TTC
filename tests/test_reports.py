"""Репорт живёт дольше одного сообщения.

Раньше жалоба уходила в чат админов и там же заканчивалась: разобрать её можно
было только сразу, а человек, потративший время на описание проблемы, не узнавал
ни что её увидели, ни что починили. Здесь проверяется то, что делает репорт
работой, а не разовым криком: номер, статус, переписка и — главное — что автору
про каждый поворот сообщают.

Отдельно проверяется набор кнопок под карточкой. Он зависит от статуса, и
ошибиться тут легко: кнопка «✅ Готово» под уже закрытым репортом отправила бы
человеку второе «всё готово» по тому же поводу.
"""

from __future__ import annotations

import asyncio
from datetime import date

import pytest

from bot import limits, texts
from bot.db.models import Report, ReportMessage, User
from bot.enums import CLOSED_REPORT_STATUSES, PermissionModule, ReportStatus, UserRole
from bot.keyboards.common_kb import admin_sections
from bot.keyboards.report_kb import report_card_kb
from bot.routers.admin import report_review
from bot.services import permission_service, report_service, scenario_service


def _report(**kwargs) -> Report:
    fields = {
        "report_id": 7,
        "author_tg_id": 100,
        "author_name": "Аня",
        "text": "Кнопка «Афиша» не открывается",
        "status": ReportStatus.NEW,
    }
    fields.update(kwargs)
    return Report(**fields)


def _author() -> User:
    return User(
        tg_id=100,
        display_name="Аня",
        username="anya",
        birth_date=date(2003, 5, 1),
        current_role=UserRole.USER,
    )


def _message(from_admin: bool, name: str, text: str) -> ReportMessage:
    return ReportMessage(report_id=7, from_admin=from_admin, author_name=name, text=text)


# --- Карточка ---------------------------------------------------------------


def test_card_shows_the_number_people_are_told() -> None:
    """Номер — не украшение: его называют человеку в личке и вслух."""
    card = report_service.card_text(_report(), _author(), [])
    assert "№7" in card
    assert "Кнопка «Афиша» не открывается" in card


def test_card_names_the_author_even_after_deletion() -> None:
    """Автора удалили — жалоба не должна стать анонимной."""
    card = report_service.card_text(_report(author_tg_id=None), None, [])
    assert "Аня" in card
    assert "удалена" in card


def test_card_shows_who_said_what() -> None:
    messages = [
        _message(True, "Админ", "А на каком экране это было?"),
        _message(False, "Аня", "В Афише, после нажатия на карточку"),
    ]
    card = report_service.card_text(_report(), _author(), messages)
    assert "А на каком экране это было?" in card
    assert "В Афише, после нажатия на карточку" in card
    assert "Админ" in card and "Аня" in card


def test_card_keeps_only_the_tail_of_a_long_talk() -> None:
    """У сообщения есть предел длины — вся переписка в карточку не влезет."""
    messages = [_message(True, "Админ", f"реплика {i}") for i in range(10)]
    card = report_service.card_text(_report(), _author(), messages)
    assert "реплика 9" in card
    assert "реплика 0" not in card
    # Про спрятанное сказано прямо, иначе кажется, что разговора не было.
    assert str(10 - limits.REPORT_CARD_TALK_SHOWN) in card


def test_card_cuts_a_very_long_reply() -> None:
    card = report_service.card_text(_report(), _author(), [_message(True, "Админ", "я" * 500)])
    assert "…" in card
    assert "я" * 500 not in card


def test_card_escapes_what_people_wrote() -> None:
    """Карточка уходит с HTML-разметкой: чужие угловые скобки её ломают."""
    card = report_service.card_text(_report(text="<b>жирный</b> баг"), _author(), [])
    assert "&lt;b&gt;" in card
    assert "<b>жирный</b>" not in card


def test_every_status_has_a_human_label() -> None:
    """Статус без подписи вывалился бы ошибкой прямо при показе карточки."""
    for status in ReportStatus:
        assert texts.REPORT_STATUS_LABELS[status.value]


# --- Кнопки под карточкой ---------------------------------------------------


def _labels(report: Report) -> set[str]:
    return {
        button.text for row in report_card_kb(report).inline_keyboard for button in row
    }


def test_new_report_offers_every_decision() -> None:
    assert _labels(_report()) == {
        texts.BTN.REPORT_REPLY,
        texts.BTN.REPORT_PROGRESS,
        texts.BTN.REPORT_DONE,
        texts.BTN.REPORT_DECLINE,
    }


def test_report_in_progress_is_not_offered_to_be_taken_again() -> None:
    assert texts.BTN.REPORT_PROGRESS not in _labels(_report(status=ReportStatus.IN_PROGRESS))


@pytest.mark.parametrize("status", sorted(CLOSED_REPORT_STATUSES, key=lambda s: s.value))
def test_closed_report_offers_no_second_closing(status: ReportStatus) -> None:
    """Второе «✅ Готово» отправило бы человеку ту же новость дважды."""
    labels = _labels(_report(status=status))
    assert texts.BTN.REPORT_DONE not in labels
    assert texts.BTN.REPORT_DECLINE not in labels
    # Ответить и вернуть в работу можно всегда: решение админа не приговор.
    assert texts.BTN.REPORT_REPLY in labels
    assert texts.BTN.REPORT_PROGRESS in labels


def test_answering_always_stays_available_to_admins() -> None:
    for status in ReportStatus:
        assert texts.BTN.REPORT_REPLY in _labels(_report(status=status))


# --- Автору сообщают о каждом повороте --------------------------------------


def test_every_decision_button_leads_to_a_status() -> None:
    """Кнопка без статуса упала бы по ключу прямо при нажатии."""
    assert set(report_review._ACTION_STATUS) == {"progress", "done", "decline"}


def test_every_status_change_tells_the_author() -> None:
    for status in report_review._ACTION_STATUS.values():
        assert status in report_service.STATUS_SCENARIO


def test_notifications_are_editable_scenarios() -> None:
    """Тексты автору правятся суперадмином, а не программистом."""
    keys = set(report_service.STATUS_SCENARIO.values()) | {"report_reply", "report_sent"}
    unknown = sorted(keys - set(scenario_service.SCENARIOS))
    assert not unknown, f"Сценарии, которых нет в реестре: {unknown}"


def test_the_progress_notice_says_work_has_started() -> None:
    """Это ровно то, чего просил владелец: «над вашим репортом началась работа»."""
    assert "работа" in texts.REPORT_PROGRESS_DM
    assert "{number}" in texts.REPORT_PROGRESS_DM


@pytest.mark.parametrize("delivery", list(scenario_service.Delivery))
def test_admin_learns_whether_the_author_got_it(delivery) -> None:
    """Молча проглоченная недоставка — это админ, уверенный, что человек в курсе."""
    assert report_review._STATUS_NOTE[delivery]
    assert report_review._REPLY_NOTE[delivery]


def test_failed_delivery_is_worded_differently_for_status_and_reply() -> None:
    """«Ответ не дошёл» про нажатие «✅ Готово» сбивало бы с толку."""
    failed = scenario_service.Delivery.FAILED
    assert report_review._STATUS_NOTE[failed] != report_review._REPLY_NOTE[failed]


# --- Права ------------------------------------------------------------------


def test_reports_are_a_separate_duty() -> None:
    assert PermissionModule.REPORTS.value in permission_service.MODULES


def test_the_section_shows_up_only_with_the_module() -> None:
    admin = User(
        tg_id=5,
        display_name="Админ",
        birth_date=date(2000, 1, 1),
        current_role=UserRole.CUSTOM,
    )
    without = admin_sections(admin, set())
    with_module = admin_sections(admin, {PermissionModule.REPORTS.value})
    assert texts.BTN.ADMIN_PANEL_REPORTS not in without
    assert texts.BTN.ADMIN_PANEL_REPORTS in with_module


def test_full_admin_gets_reports_without_any_setup() -> None:
    """Иначе после выкатки репорты некому было бы разбирать до раздачи прав."""
    admin = User(
        tg_id=6,
        display_name="Полный админ",
        birth_date=date(2000, 1, 1),
        current_role=UserRole.ADMIN,
    )
    # Полному админу модули не выдают — он получает все, база тут не нужна.
    modules = asyncio.run(permission_service.effective_modules(None, admin))
    assert PermissionModule.REPORTS.value in modules
