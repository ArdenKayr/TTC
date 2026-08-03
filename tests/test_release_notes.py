"""Сторож правил обновлений (docs/RELEASE_RULES.md).

Правила — это шесть договорённостей о том, как выпускается обновление. Пять из
шести можно проверить машинально, и здесь они проверяются: у обновления есть
номер и название, обе страницы (участникам и админам) написаны и непусты,
каждый пункт начинается с сути в одну строку, а названия кнопок в тексте
совпадают с настоящими кнопками бота.

Последнее — не придирка. Статья живёт в Telegraph, отдельно от кода: кнопку
переименуют, а статья останется рассказывать про старую. Здесь это ловится
сразу: тест падает, пока текст не догонит бота.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from bot import texts
from scripts.build_release import (
    ADMINS_MARKER,
    RELEASES,
    USERS_MARKER,
    build_one,
    parse,
    sources,
)
from scripts.telegraph import TelegraphError

ROOT = Path(__file__).resolve().parent.parent

# Теги, которые Telegraph сохраняет при вставке. Всё остальное он выбросит.
TELEGRAPH_TAGS = {"a", "b", "blockquote", "code", "em", "h3", "h4", "hr", "i",
                  "li", "ol", "p", "s", "strong", "u", "ul"}

# Подписи всех кнопок бота.
BUTTONS = {
    value
    for name, value in vars(texts.BTN).items()
    if not name.startswith("_") and isinstance(value, str)
}

# «📄 Разделы» — упоминание кнопки; «Афиша» — просто слово. Отличаем по первому
# символу: у кнопок это эмодзи.
_QUOTED = re.compile(r"«([^»\n]{1,60})»")
_HEADING = re.compile(r"^###\s+(.*)$", re.MULTILINE)

# Обороты, по которым видно, что текст писала нейросеть, а не человек.
# Правило 3: «пишешь как человек», сухо и по делу.
_CLICHES = (
    "мы рады",
    "рады сообщить",
    "рады представить",
    "пользовательский опыт",
    "в рамках данного",
    "не может не радовать",
    "стало ещё удобнее",
)


def _looks_like_button(quoted: str) -> bool:
    head = quoted[0]
    return not (head.isalnum() or head in "/«»")


def _ids(paths):
    return [path.name for path in paths]


def test_there_is_at_least_one_release():
    """Без файла обновления регламент не с чем сверять."""
    assert sources(), f"в {RELEASES} нет ни одного файла обновления"


@pytest.mark.parametrize("path", sources(), ids=_ids(sources()))
def test_release_has_name_and_both_parts(path):
    """Правила 1, 3, 4: номер, название, дата и обе страницы."""
    release = parse(path.read_text(encoding="utf-8"), path)
    assert release.number > 0
    assert release.title.strip()
    assert release.date.strip()
    assert release.users.strip()
    assert release.admins.strip()


@pytest.mark.parametrize("path", sources(), ids=_ids(sources()))
def test_every_item_starts_with_the_point(path):
    """Правило 3: сначала суть в одну строку, затем пояснение."""
    release = parse(path.read_text(encoding="utf-8"), path)
    for part_name, part in (("участникам", release.users), ("админам", release.admins)):
        headings = _HEADING.findall(part)
        assert headings, f"в части «{part_name}» файла {path.name} нет ни одного пункта"
        for heading in headings:
            assert len(heading) <= 90, (
                f"суть пункта не помещается в строку ({len(heading)} символов): {heading}"
            )
        # После каждого заголовка должно идти пояснение, а не сразу следующий пункт.
        blocks = re.split(r"^###\s+.*$", part, flags=re.MULTILINE)[1:]
        for heading, body in zip(headings, blocks):
            assert body.strip(), f"пункт «{heading}» в {path.name} остался без пояснения"


@pytest.mark.parametrize("path", sources(), ids=_ids(sources()))
def test_buttons_in_text_exist_in_the_bot(path):
    """Названия кнопок в статье — те же, что у бота."""
    text = path.read_text(encoding="utf-8")
    mentioned = {q for q in _QUOTED.findall(text) if _looks_like_button(q)}
    unknown = mentioned - BUTTONS
    assert not unknown, (
        f"в {path.name} упомянуты кнопки, которых нет в bot/texts.py: {sorted(unknown)}\n"
        "Либо опечатка, либо кнопку переименовали, а статья осталась со старым названием."
    )


@pytest.mark.parametrize("path", sources(), ids=_ids(sources()))
def test_written_like_a_human(path):
    """Правило 3: без нейросетевых оборотов."""
    lowered = path.read_text(encoding="utf-8").lower()
    found = [cliche for cliche in _CLICHES if cliche in lowered]
    assert not found, f"в {path.name} штампы вместо нормального текста: {found}"


@pytest.mark.parametrize("path", sources(), ids=_ids(sources()))
def test_pages_survive_telegraph(path):
    """Собранные страницы состоят только из того, что Telegraph не выбросит."""
    _, pages = build_one(path)
    try:
        for page_path in pages:
            html = page_path.read_text(encoding="utf-8")
            article = html.split('<main id="article">', 1)[1].split("</main>", 1)[0]
            for tag in set(re.findall(r"</?([a-z0-9]+)", article)):
                assert tag in TELEGRAPH_TAGS, f"{page_path.name}: Telegraph выбросит <{tag}>"
            for leftover in ("###", "**", "<!--"):
                assert leftover not in article, (
                    f"{page_path.name}: в тексте осталась разметка «{leftover}» — "
                    "в статью она попадёт как есть"
                )
    finally:
        for page_path in pages:
            page_path.unlink(missing_ok=True)


def test_built_pages_are_not_stored_in_git():
    """Страницы выводятся из .md целиком, держать их в git незачем."""
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "docs/releases/*.html" in ignored


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Дата: 3 августа 2026\n<!-- участникам -->\nа\n<!-- админам -->\nб", "заголовка обновления"),
        ("# Обновление 1 — «Тест»\n<!-- участникам -->\nа\n<!-- админам -->\nб", "датой"),
        ("# Обновление 1 — «Тест»\nДата: сегодня\n<!-- админам -->\nб", "границы"),
        (
            "# Обновление 1 — «Тест»\nДата: сегодня\n<!-- участникам -->\n\n<!-- админам -->\nб",
            "пустая",
        ),
        (
            "# Обновление 1 — «Тест»\nДата: сегодня\n<!-- админам -->\nб\n<!-- участникам -->\nа",
            "перепутаны",
        ),
    ],
)
def test_errors_explain_what_to_fix(text, expected):
    """Ошибку читает не программист — она должна говорить, что дописать."""
    with pytest.raises(TelegraphError) as error:
        parse(text, Path("01-проверка.md"))
    assert expected in str(error.value)


def test_markers_are_plain_markdown_comments():
    """Границы частей не должны попадать в статью и мешать читать исходник."""
    for marker in (USERS_MARKER, ADMINS_MARKER):
        assert marker.startswith("<!--") and marker.endswith("-->")
