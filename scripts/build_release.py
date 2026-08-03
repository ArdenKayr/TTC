"""Собирает из файла обновления две страницы: участникам и админам.

Правила обновлений (docs/RELEASE_RULES.md) требуют по итогам каждого обновления
две статьи в Telegraph: одну для участников сообщества, вторую для админов и
суперадминов. Писать их в двух файлах — верный способ получить два разных
описания одного и того же изменения, поэтому исходник один:

    docs/releases/NN-slug.md

В нём две части, разделённые строками-границами «участникам» и «админам».
Всё, что выше первой границы, — служебное: заголовок обновления, дата, заметки
о том, что проверить после выкатки. В статьи это не попадает.

Запуск: двойной клик по «обновление.bat» в корне проекта.
"""

from __future__ import annotations

import re
import sys
import webbrowser
from dataclasses import dataclass
from pathlib import Path

from scripts.telegraph import TelegraphError, convert, page

ROOT = Path(__file__).resolve().parent.parent
RELEASES = ROOT / "docs" / "releases"

# Границы частей. Каждая — обычный комментарий Markdown, поэтому исходник
# остаётся читаемым сам по себе, без сборки.
USERS_MARKER = "<!-- участникам -->"
ADMINS_MARKER = "<!-- админам -->"

# «# Обновление 1 — «Только кнопки»»: номер и название (правило 1).
_TITLE = re.compile(r"^#\s*Обновление\s+(\d+)\s*[—–-]\s*[«\"](.+?)[»\"]\s*$", re.MULTILINE)
_DATE = re.compile(r"^Дата:\s*(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class Release:
    """Разобранный файл обновления."""

    number: int
    title: str
    date: str
    users: str
    admins: str
    source: Path

    @property
    def full_name(self) -> str:
        return f"Обновление {self.number} «{self.title}»"


def parse(text: str, source: Path) -> Release:
    """Файл обновления -> его части. Ошибки объясняют, что дописать."""
    title = _TITLE.search(text)
    if not title:
        raise TelegraphError(
            f"В {source.name} нет заголовка обновления.\n"
            "Первая строка файла должна выглядеть так:\n"
            "  # Обновление 1 — «Только кнопки»\n"
            "Номер и название обязательны — это правило 1 регламента обновлений."
        )
    date = _DATE.search(text)
    if not date:
        raise TelegraphError(
            f"В {source.name} нет строки с датой.\nДобавьте её под заголовком:\n"
            "  Дата: 3 августа 2026"
        )

    for marker in (USERS_MARKER, ADMINS_MARKER):
        if marker not in text:
            raise TelegraphError(
                f"В {source.name} нет строки-границы {marker}\n"
                "Файл делится на две части: то, что читают участники, и то, что читают "
                "админы. Без границы непонятно, где кончается одна и начинается другая."
            )
    if text.index(USERS_MARKER) > text.index(ADMINS_MARKER):
        raise TelegraphError(
            f"В {source.name} части перепутаны местами: {USERS_MARKER} должна идти "
            f"раньше, чем {ADMINS_MARKER}."
        )

    users = text.split(USERS_MARKER, 1)[1].split(ADMINS_MARKER, 1)[0]
    admins = text.split(ADMINS_MARKER, 1)[1]
    for name, part in (("участникам", users), ("админам", admins)):
        if not part.strip():
            raise TelegraphError(
                f"В {source.name} часть «{name}» пустая.\n"
                "Правила обновлений требуют обе страницы: одну для участников, "
                "вторую для админов и суперадминов."
            )

    return Release(
        number=int(title.group(1)),
        title=title.group(2).strip(),
        date=date.group(1),
        users=users,
        admins=admins,
        source=source,
    )


def _write(release: Release, part: str, body: str, audience: str, note: str) -> Path:
    target = release.source.with_suffix(f".{part}.html")
    article_title = f"{release.full_name} — {audience}"
    extra = f"<br>Это страница <b>{note}</b>. Дата обновления: {release.date}."
    target.write_text(
        page(article_title, convert(body, release.source.name), extra), encoding="utf-8"
    )
    return target


def build_one(source: Path) -> tuple[Release, list[Path]]:
    release = parse(source.read_text(encoding="utf-8"), source)
    pages = [
        _write(release, "users", release.users, "что изменилось", "для участников"),
        _write(release, "admins", release.admins, "для админов", "для админов и суперадминов"),
    ]
    return release, pages


def sources() -> list[Path]:
    return sorted(RELEASES.glob("*.md"))


def latest() -> Path:
    found = sources()
    if not found:
        raise TelegraphError(
            f"В {RELEASES} нет ни одного файла обновления.\n"
            "Заведите docs/releases/01-название.md по образцу из docs/RELEASE_RULES.md."
        )
    return found[-1]


def main() -> int:
    try:
        # Собираем все: старые статьи иногда нужно пересобрать (переименовали
        # кнопку — текст статьи должен догнать бота).
        built = [build_one(path) for path in sources()]
        newest = build_one(latest())
    except TelegraphError as error:
        print(f"Не получилось собрать страницы обновления.\n\n{error}")
        return 1

    for release, pages in built:
        print(f"{release.full_name} ({release.date}):")
        for target in pages:
            print(f"  {target}")
    print("\nОткрываю последнее обновление. В каждой странице — кнопка «Скопировать")
    print("текст статьи»: нажать, вставить в telegra.ph, заголовок вписать отдельно.")
    for target in newest[1]:
        webbrowser.open(target.as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
