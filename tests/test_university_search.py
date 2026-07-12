"""Нормализация поискового запроса вуза: пунктуация, пробелы, спецсимволы."""

import pytest

from bot.db.repositories.university_repo import normalize_query


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("СПбГУ", "СПбГУ"),
        ("СПбГУ!!!", "СПбГУ"),
        ("  много   пробелов  ", "много пробелов"),
        ("Санкт-Петербургский гос. университет", "Санкт Петербургский гос университет"),
        ("политех?", "политех"),
        ("«ИТМО»", "ИТМО"),
        ("???", ""),
        ("", ""),
    ],
)
def test_normalize_query(raw: str, expected: str) -> None:
    assert normalize_query(raw) == expected


def test_normalize_keeps_case() -> None:
    # Регистр не меняем — его игнорирует сам pg_trgm.
    assert normalize_query("СпБгУ") == "СпБгУ"
