from datetime import date

import pytest

from bot import texts
from bot.db.models import User, VoteRequest
from bot.enums import UserRole
from bot.services.activity_service import anonymity_line, build_vote_card, parse_vote_options


def test_two_options_parsed() -> None:
    assert parse_vote_options("Да\nНет") == ["Да", "Нет"]


def test_blank_lines_and_spaces_ignored() -> None:
    assert parse_vote_options("  Поход  \n\n\n  Кино  \n") == ["Поход", "Кино"]


def test_single_option_rejected() -> None:
    assert parse_vote_options("Только один вариант") is None


def test_too_many_options_rejected() -> None:
    assert parse_vote_options("\n".join(f"Вариант {i}" for i in range(11))) is None


def test_ten_options_accepted() -> None:
    options = parse_vote_options("\n".join(f"Вариант {i}" for i in range(10)))
    assert options is not None and len(options) == 10


def test_too_long_option_rejected() -> None:
    assert parse_vote_options("Да\n" + "х" * 101) is None


@pytest.mark.parametrize("raw", ["", "\n\n", "   "])
def test_empty_input_rejected(raw: str) -> None:
    assert parse_vote_options(raw) is None


# --- Анонимность опроса ---


def _author() -> User:
    return User(
        tg_id=1,
        username="ivan",
        display_name="Ваня",
        birth_date=date(2000, 1, 1),
        current_role=UserRole.USER,
    )


def test_anonymity_line_differs() -> None:
    assert anonymity_line(True) == texts.VOTE_ANON_LINE_YES
    assert anonymity_line(False) == texts.VOTE_ANON_LINE_NO
    assert anonymity_line(True) != anonymity_line(False)


@pytest.mark.parametrize("is_anonymous", [True, False])
def test_admin_card_states_poll_type(is_anonymous: bool) -> None:
    """Админ должен видеть тип опроса до одобрения — поменять его потом нельзя."""
    card = build_vote_card(_author(), "Куда едем?", ["Лес", "Море"], is_anonymous)
    assert anonymity_line(is_anonymous) in card
    assert "Куда едем?" in card


def test_vote_request_defaults_to_anonymous() -> None:
    """Старые заявки и всё, что создаётся без явного выбора, остаются анонимными."""
    request = VoteRequest(tg_id=1, question="Вопрос", options=["Да", "Нет"])
    assert request.is_anonymous is None  # значение проставит база (server_default)
    assert VoteRequest.__table__.columns["is_anonymous"].default.arg is True
