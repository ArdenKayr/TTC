"""«Что нужно, чтобы мероприятие состоялось».

Обязательный шаг анкеты мероприятия: организатор пишет свободным текстом, что
требуется — люди, деньги, помещение, реквизит. Свободным, а не набором полей,
потому что заранее не угадать: одному нужны 15 человек и зал, другому
100 000 ₽, третьему три помощника с реквизитом.

Строка идёт первой среди деталей — и в карточке админам, и в Афише: именно по
ней человек понимает, чем может помочь.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from bot import limits, texts
from bot.db.models import Activity, ActivityRequest, User
from bot.enums import ActivityStatus, UserRole
from bot.services.activity_service import _afisha_text, act_details, build_act_card

NEEDS = "15 участников, из них 5 помогают; 100 000 ₽ на аренду; зал на 20 человек"


@pytest.fixture
def author() -> User:
    return User(
        tg_id=42,
        username="organizer",
        display_name="Организатор",
        birth_date=date(2000, 1, 1),
        current_role=UserRole.USER,
    )


def test_needs_line_comes_first():
    """По этой строке решают, идти ли помогать, — она не должна теряться внизу."""
    details = act_details("@kto-to", "https://plan", "https://chat", "комментарий", needs_text=NEEDS)
    lines = [line for line in details.splitlines() if line]
    assert NEEDS in lines[0]


def test_details_without_needs_have_no_empty_line():
    """У мероприятий, поданных до этого шага, поля просто нет."""
    details = act_details("@kto-to", None, None)
    assert "Что нужно" not in details


def test_needs_are_escaped():
    """Текст пишет человек — угловые скобки не должны ломать сообщение."""
    details = act_details(None, None, None, needs_text="зал <на 20 человек>")
    assert "<на" not in details
    assert "&lt;на" in details


def test_admin_card_shows_needs(author):
    request = ActivityRequest(
        request_id=uuid.uuid4(),
        tg_id=author.tg_id,
        title="Квиз",
        description="Игра для своих",
        needs_text=NEEDS,
    )
    assert NEEDS in build_act_card(author, request)


def test_afisha_card_shows_needs(author):
    activity = Activity(
        activity_id=uuid.uuid4(),
        organizer_id=author.tg_id,
        title="Квиз",
        description="Игра для своих",
        needs_text=NEEDS,
        status=ActivityStatus.ACTIVE,
    )
    assert NEEDS in _afisha_text(activity, author)


def test_prompt_explains_what_to_write():
    """Человек должен понять, что писать, без догадок."""
    prompt = texts.ACT_NEEDS_PROMPT.format(
        min=limits.ACT_NEEDS_MIN, max=limits.ACT_NEEDS_MAX
    )
    for word in ("люди", "деньги", "помещение"):
        assert word in prompt.lower()
    assert str(limits.ACT_NEEDS_MAX) in prompt


def test_step_is_mandatory():
    """Пропуска у этого шага нет — иначе поле осталось бы пустым у половины заявок."""
    prompt = texts.ACT_NEEDS_PROMPT.format(
        min=limits.ACT_NEEDS_MIN, max=limits.ACT_NEEDS_MAX
    )
    assert texts.BTN.SKIP not in prompt
