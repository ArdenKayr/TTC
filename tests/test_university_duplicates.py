"""Карточка заявки на вуз обязана показать похожие записи справочника.

13–14 сентября 2026 года в справочник уехало шесть двойников: «РГПУ им.
Герцена» рядом с настоящей записью Герцена, два СПбГАСУ, ещё один СПбГУ с
полным официальным названием. Одобряющий не видел, что такой вуз уже заведён:
карточка показывала только то, что прислал человек. Дальше двойник сам начинал
находиться в поиске и собирать людей — запись Герцена-двойника за пять дней
собрала десять человек, а всего в несуществующих вузах оказалось 23 человека.

Точное совпадение названия ловил и `approve_request`, но двойник почти никогда
не совпадает точно: у настоящей записи название длинное и официальное, а
человек пишет сокращение. Поэтому похожесть ищется тем же поиском, каким ищет
вуз сам человек, и по названию, и по каждому предложенному варианту поиска.
"""

from __future__ import annotations

import asyncio

import pytest

from bot import texts
from bot.db.models import University
from bot.db.repositories import university_repo
from bot.services import university_service

HERZEN = "Российский государственный педагогический университет им. А. И. Герцена"


class _Request:
    """Заявка на вуз: только то, из чего собирается карточка."""

    def __init__(self, name: str, aliases: list[str] | None = None) -> None:
        self.name = name
        self.aliases = aliases or []
        self.applicant_name = "Даниил"
        self.applicant_username = "danya"
        self.tg_id = 1487102081
        self.link = "https://herzen.spb.ru"


def _uni(university_id: int, name: str) -> University:
    return University(university_id=university_id, canonical_name=name)


def _search_returning(answers: dict[str, list[University]], asked: list[str]):
    """Подставной поиск: отвечает по заранее заданным запросам и их запоминает."""

    async def search(session, query: str, limit: int = 5) -> list[University]:
        asked.append(query)
        return answers.get(query, [])[:limit]

    return search


def _card(monkeypatch, request: _Request, answers: dict[str, list[University]]) -> str:
    asked: list[str] = []
    monkeypatch.setattr(university_repo, "search", _search_returning(answers, asked))
    card = asyncio.run(university_service.render_request_card(object(), request))
    request.asked = asked  # чтобы тест мог проверить, о чём спрашивали поиск
    return card


def test_similar_entry_is_shown(monkeypatch) -> None:
    request = _Request("РГПУ им. Герцена", ["РГПУ", "ГЕРЦЕНА"])
    card = _card(monkeypatch, request, {"РГПУ им. Герцена": [_uni(11, HERZEN)]})
    assert "Похожее в справочнике уже есть" in card
    assert HERZEN in card
    assert "id <code>11</code>" in card


def test_nothing_similar_means_no_warning(monkeypatch) -> None:
    request = _Request("Московский Государственный Университет им. М.В. Ломоносова", ["МГУ"])
    card = _card(monkeypatch, request, {})
    assert "Похожее в справочнике уже есть" not in card
    # Сама карточка при этом целая.
    assert "Заявка на добавление вуза" in card
    assert "МГУ" in card


def test_alias_finds_what_name_missed(monkeypatch) -> None:
    """Двойник выдаёт себя сокращением: по названию поиск молчит, по «СПбГАСУ» — нет."""
    gasu = "Санкт-Петербургский государственный архитектурно-строительный университет"
    request = _Request("Санкт-Петербургский Архитектурно-Строительный Университет", ["СПбГАСУ"])
    card = _card(monkeypatch, request, {"СПбГАСУ": [_uni(10, gasu)]})
    assert gasu in card
    assert request.asked == [
        "Санкт-Петербургский Архитектурно-Строительный Университет",
        "СПбГАСУ",
    ]


def test_same_entry_listed_once(monkeypatch) -> None:
    request = _Request("РГПУ им. Герцена", ["РГПУ", "ГЕРЦЕНА"])
    herzen = [_uni(11, HERZEN)]
    card = _card(
        monkeypatch,
        request,
        {"РГПУ им. Герцена": herzen, "РГПУ": herzen, "ГЕРЦЕНА": herzen},
    )
    assert card.count(HERZEN) == 1


def test_no_more_than_three(monkeypatch) -> None:
    request = _Request("Университет", [])
    many = [_uni(i, f"Вуз номер {i}") for i in range(1, 8)]
    card = _card(monkeypatch, request, {"Университет": many})
    assert card.count("• Вуз номер") == university_service.SIMILAR_LIMIT


def test_name_is_escaped(monkeypatch) -> None:
    request = _Request("Хитрый вуз", [])
    card = _card(monkeypatch, request, {"Хитрый вуз": [_uni(5, "Вуз <b>жирный</b> & Ко")]})
    assert "&lt;b&gt;" in card
    assert "<b>жирный" not in card


@pytest.mark.parametrize("aliases", [[], None])
def test_request_without_aliases(monkeypatch, aliases) -> None:
    """Заявку без вариантов поиска всё равно проверяем — по названию."""
    request = _Request("РГПУ им. Герцена", aliases)
    card = _card(monkeypatch, request, {"РГПУ им. Герцена": [_uni(11, HERZEN)]})
    assert HERZEN in card
    assert request.asked == ["РГПУ им. Герцена"]


def test_texts_keep_placeholders() -> None:
    """Шаблон не должен потерять подстановки — иначе карточка упадёт на format."""
    assert "{items}" in texts.UNI_REQ_SIMILAR
    assert "{name}" in texts.UNI_REQ_SIMILAR_ITEM
    assert "{uni_id}" in texts.UNI_REQ_SIMILAR_ITEM
