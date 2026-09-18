"""Слово «Готово», написанное руками, — это конец списка, а не вариант поиска.

В справочнике вузов 18.09.2026 нашёлся вариант поиска «Готово»: у СПбГУПТД он
лежал рядом с настоящими сокращениями. Приехал он с шага, где человек
присылает свои сокращения: кнопка подписана «Готово ➡️», а сравнение было
точным, и написанное руками «Готово» уходило дальше обычным вариантом.

Отсюда терпимое сравнение: буквы важны, эмодзи и знаки — нет.
"""

from __future__ import annotations

import pytest

from bot import texts
from bot.routers.registration import _means_done


@pytest.mark.parametrize(
    "text",
    [
        "Готово ➡️",  # сама кнопка
        "Готово",
        "готово",
        "ГОТОВО",
        "  готово  ",
        "готово!",
        "✅ Готово",
        "готово.",
    ],
)
def test_means_done(text: str) -> None:
    assert _means_done(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "Готовность",
        "готов",
        "гото во",
        "готово2",
        "СПбГУ",
        "",
        "➡️",
    ],
)
def test_not_done(text: str) -> None:
    assert _means_done(text) is False


def test_button_label_is_recognized() -> None:
    """Кнопку переименовали во что-то, чего сравнение не ловит, — это ошибка."""
    assert _means_done(texts.BTN.ALIAS_DONE)
