import pytest

from bot.services.activity_service import parse_vote_options


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
