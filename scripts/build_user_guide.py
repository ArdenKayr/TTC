"""Собирает из docs/USER_GUIDE.md страницу, которую принимает Telegraph.

Правила разметки общие для всех статей проекта и живут в scripts/telegraph.py —
здесь только то, что относится к инструкции участника: где лежит исходник, где
у него начинается текст статьи и как называется статья в Telegraph.

Запуск: двойной клик по «инструкция.bat» в корне проекта.
"""

from __future__ import annotations

import sys
from pathlib import Path

from scripts.telegraph import TelegraphError, inline, page
from scripts.telegraph import convert as _convert

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "USER_GUIDE.md"
TARGET = ROOT / "docs" / "USER_GUIDE.html"

# Всё, что выше этой строки в исходнике, — служебные пояснения для владельца,
# а не текст статьи. Граница задана явно, чтобы её нельзя было сдвинуть случайно.
MARKER = "<!-- начало статьи"

# Заголовок статьи Telegraph спрашивает отдельным полем, поэтому в теле его нет.
ARTICLE_TITLE = "Бот сообщества «Истинный Курс» — как всё устроено"

# Историческое имя ошибки: на него ссылаются тесты и текст bat-файла.
GuideError = TelegraphError

__all__ = ["ARTICLE_TITLE", "MARKER", "SOURCE", "TARGET", "GuideError", "build", "convert", "inline"]


def convert(markdown: str) -> str:
    """Отрезает служебное вступление и собирает статью."""
    if MARKER not in markdown:
        raise GuideError(
            f"В {SOURCE.name} нет строки-границы «{MARKER}...».\n"
            "Она отделяет служебное пояснение от текста статьи — без неё "
            "непонятно, что переносить в Telegraph."
        )
    body = markdown.split(MARKER, 1)[1].split("-->", 1)[-1]
    return _convert(body, SOURCE.name)


def build() -> Path:
    if not SOURCE.exists():
        raise GuideError(f"Не найден исходник статьи: {SOURCE}")
    TARGET.write_text(page(ARTICLE_TITLE, convert(SOURCE.read_text(encoding="utf-8"))), encoding="utf-8")
    return TARGET


def main() -> int:
    try:
        target = build()
    except GuideError as error:
        print(f"Не получилось собрать страницу.\n\n{error}")
        return 1
    blocks = target.read_text(encoding="utf-8").count("\n<")
    print(f"Страница для статьи собрана: {target}")
    print(f"  блоков текста: {blocks}")
    print("  откройте её, нажмите «Скопировать текст статьи» и вставьте в telegra.ph")
    return 0


if __name__ == "__main__":
    sys.exit(main())
