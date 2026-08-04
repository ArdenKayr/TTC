"""Сторож инструкции для участников.

Инструкция живёт в Markdown, а попадает в Telegraph через собранную страницу.
Telegraph — редактор придирчивый: Markdown он не понимает вовсе, а из HTML
оставляет только теги из своего короткого списка, остальное молча выбрасывает.
«Молча» здесь главное слово: текст вставится, выглядеть будет почти правильно,
и заметить пропажу можно только вычитав статью целиком.

Поэтому проверяем машинально: в собранной странице не осталось markdown-символов,
не появилось тегов, которые Telegraph выбросит, и ни один заголовок исходника
не потерялся по дороге.
"""

from __future__ import annotations

import re

import pytest

from scripts.build_user_guide import (
    MARKER,
    SOURCE,
    GuideError,
    convert,
    inline,
)

# Теги, которые Telegraph сохраняет при вставке. Всё остальное он выбросит,
# поэтому генератору незачем их создавать.
TELEGRAPH_TAGS = {
    "a", "aside", "b", "blockquote", "br", "code", "em", "figcaption", "figure",
    "h3", "h4", "hr", "i", "iframe", "img", "li", "ol", "p", "pre", "s",
    "strong", "u", "ul", "video",
}

# Слова, которыми текст незаметно превращается в рассказ об истории проекта.
# «Прежняя ссылка» сюда не входит намеренно: это про ссылку самого человека,
# а не про прошлую версию бота.
PAST_REFERENCES = ("раньше", "теперь", "больше не", "по-прежнему", "до обновления")


@pytest.fixture(scope="module")
def markdown() -> str:
    return SOURCE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def article(markdown: str) -> str:
    return convert(markdown)


def test_source_marks_where_the_article_starts(markdown: str) -> None:
    """Без границы непонятно, где служебные пояснения, а где текст статьи."""
    assert MARKER in markdown, (
        f"В {SOURCE.name} потерялась строка-граница «{MARKER}...» — "
        "по ней сборщик отделяет пояснения для владельца от самой статьи."
    )


def test_the_guide_does_not_look_back(markdown: str) -> None:
    """Инструкция описывает бота таким, какой он есть, — и только.

    Её читает человек, который видит бота впервые: «раньше было так, а теперь
    иначе» ему не нужно и только мешает разбираться. История изменений живёт
    отдельно, на страницах обновлений, — там она и интересна.
    """
    body = markdown.split(MARKER, 1)[1].lower()
    found = sorted(word for word in PAST_REFERENCES if word in body)
    assert not found, (
        f"В тексте статьи есть оглядка на прошлые версии бота: {found}. "
        "Опишите настоящим временем, как всё устроено сейчас; что именно "
        "изменилось — место в docs/releases/."
    )


def test_no_tables_in_source(markdown: str) -> None:
    """Таблицы Telegraph не поддерживает — при вставке они просто исчезнут."""
    body = markdown.split(MARKER, 1)[1]
    rows = [line for line in body.splitlines() if line.strip().startswith("|")]
    assert not rows, (
        f"В тексте статьи есть таблица: {rows[:2]}. Telegraph таблицы теряет — "
        "перепишите её списком."
    )


def test_no_markdown_left_in_the_page(article: str) -> None:
    leftovers = {
        "жирный (**)": re.findall(r"\*\*", article),
        "заголовок (#)": re.findall(r"^#{1,6} ", article, re.MULTILINE),
        "таблица (|)": re.findall(r"^\|", article, re.MULTILINE),
        "ссылка ([]())": re.findall(r"\[[^\]]+\]\([^)]+\)", article),
    }
    broken = {name: found for name, found in leftovers.items() if found}
    assert not broken, (
        f"В собранной странице осталась markdown-разметка: {list(broken)}. "
        "В Telegraph она будет видна человеку как символы."
    )


def test_only_tags_telegraph_keeps(article: str) -> None:
    used = {tag.lower() for tag in re.findall(r"<\s*/?\s*([a-zA-Z0-9]+)", article)}
    unsupported = sorted(used - TELEGRAPH_TAGS)
    assert not unsupported, (
        f"Сборщик создал теги, которые Telegraph выбросит: {unsupported}. "
        "Оформление на их месте пропадёт без предупреждения."
    )


def test_every_heading_survives(markdown: str, article: str) -> None:
    """Заголовок, потерянный при сборке, — это потерянный раздел статьи."""
    body = markdown.split(MARKER, 1)[1]
    headings = [
        line.strip().lstrip("#").strip()
        for line in body.splitlines()
        if line.strip().startswith("#")
    ]
    assert headings, "В статье не нашлось ни одного заголовка — что-то не так с разбором."

    plain = re.sub(r"<[^>]+>", "", article)
    lost = [h for h in headings if re.sub(r"[*`]", "", h) not in plain]
    assert not lost, f"Эти заголовки не попали в собранную страницу: {lost}"


def test_headings_fit_two_levels(article: str) -> None:
    """У Telegraph всего два уровня заголовков — h3 и h4."""
    levels = set(re.findall(r"<h(\d)", article))
    assert levels <= {"3", "4"}, (
        f"В странице есть заголовки уровней {sorted(levels)}. "
        "Telegraph знает только h3 и h4, остальные превратит в обычный текст."
    )


def test_lists_are_built_from_real_items(article: str) -> None:
    """Список без пунктов — верный признак, что разбор списков сломался."""
    empty = re.findall(r"<(ul|ol)>\s*</(?:ul|ol)>", article)
    assert not empty, "В странице есть пустые списки — разбор пунктов сломан."
    assert "<li>" in article, "В статье не осталось ни одного пункта списка."


def test_missing_marker_explains_itself() -> None:
    """Ошибку читает не программист — она должна объяснять, что делать."""
    with pytest.raises(GuideError) as error:
        convert("# Заголовок\n\nТекст без границы статьи.\n")
    assert MARKER in str(error.value)


def test_table_in_source_is_reported_clearly() -> None:
    with pytest.raises(GuideError) as error:
        convert(f"{MARKER} -->\n\n| Кнопка | Что делает |\n|---|---|\n| А | Б |\n")
    assert "таблиц" in str(error.value).lower()


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("**жирный**", "<b>жирный</b>"),
        ("команда `/start`", "команда <code>/start</code>"),
        ("[текст](https://example.org)", '<a href="https://example.org">текст</a>'),
        ("знак < и &", "знак &lt; и &amp;"),
    ],
)
def test_inline_markup(source: str, expected: str) -> None:
    assert inline(source) == expected
