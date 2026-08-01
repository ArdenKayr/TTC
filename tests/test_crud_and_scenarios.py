"""Разбор значений CRUD-панели и шаблоны сценариев."""

import asyncio
from datetime import date
from pathlib import Path

import pytest
import sqlalchemy as sa

from bot.db.models import University, User
from bot.enums import UserRole
from bot.services import crud_service, scenario_service

ROOT = Path(__file__).resolve().parent.parent


def _col(model, name):
    return model.__table__.columns[name]


def test_parse_value_types():
    assert crud_service.parse_value(_col(User, "university_id"), "12") == 12
    assert crud_service.parse_value(_col(User, "display_name"), " Вася ") == "Вася"
    assert crud_service.parse_value(_col(User, "birth_date"), "03.09.2004") == date(2004, 9, 3)
    assert crud_service.parse_value(_col(User, "current_role"), "admin") is UserRole.ADMIN
    assert crud_service.parse_value(_col(University, "is_verified"), "да") is True
    assert crud_service.parse_value(_col(University, "is_verified"), "0") is False
    assert crud_service.parse_value(_col(University, "city"), "-") is None
    assert crud_service.parse_value(
        _col(User, "custom_permissions"), '{"modules": []}'
    ) == {"modules": []}


@pytest.mark.parametrize(
    ("model", "field", "raw"),
    [
        (User, "university_id", "abc"),
        (User, "birth_date", "2004-09-03"),
        (User, "current_role", "король"),
        (University, "is_verified", "может"),
        (User, "display_name", "-"),  # NOT NULL — очищать нельзя
    ],
)
def test_parse_value_invalid(model, field, raw):
    with pytest.raises(ValueError):
        crud_service.parse_value(_col(model, field), raw)


def test_tables_single_pk():
    for spec in crud_service.TABLES.values():
        assert len(sa.inspect(spec.model).primary_key) == 1, spec.code


def test_scenario_defaults_render():
    for scen in scenario_service.SCENARIOS.values():
        assert scen.group in scenario_service.GROUPS
        assert scenario_service.validate_template(scen.default), scen.key


def test_validate_template_rejects_broken_braces():
    assert not scenario_service.validate_template("Привет {")
    assert scenario_service.validate_template("Привет {name} и {unknown}")


def test_safe_params_leaves_unknown_placeholders():
    text = "А: {title}, Б: {unknown}".format_map(
        scenario_service._SafeParams({"title": "X"})
    )
    assert text == "А: X, Б: {unknown}"


# --------------------------------------------------------------------------
# Карточка записи не должна лезть в базу исподтишка
#
# Боевая ошибка 2026-08-02: после сохранения правки в CRUD бот падал с
# MissingGreenlet. Причина — колонка updated_at с onupdate=now(): её значение
# считает база, поэтому после сохранения оно помечено «непрочитанным», и
# обычное чтение obj.updated_at при отрисовке карточки уходило в базу мимо
# await. В асинхронном SQLAlchemy это падение, а не задержка.
# --------------------------------------------------------------------------


class _RefreshSpy:
    """Подставная сессия: запоминает, какие поля у неё просили дочитать."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def refresh(self, obj, attribute_names=None) -> None:
        self.calls.append(sorted(attribute_names or []))


def test_load_all_fields_asks_the_database_for_what_is_missing():
    person = User(tg_id=1, display_name="Тест")
    missing = sorted(sa.inspect(person).unloaded)
    assert missing, "У свежего объекта должны быть непрочитанные поля — иначе тест бессмыслен."

    session = _RefreshSpy()
    asyncio.run(crud_service.load_all_fields(session, person))

    assert session.calls == [missing], (
        "Перед показом карточки бот должен дочитать недостающие поля одним "
        f"явным запросом. Спросил: {session.calls}, а не хватало: {missing}."
    )


def test_load_all_fields_does_not_touch_the_database_when_nothing_is_missing():
    person = User(tg_id=1, display_name="Тест")
    # Проставляем все поля: теперь читать из базы нечего.
    for column in sa.inspect(User).columns:
        setattr(person, column.key, getattr(person, column.key, None))
    assert not sa.inspect(person).unloaded

    session = _RefreshSpy()
    asyncio.run(crud_service.load_all_fields(session, person))
    assert session.calls == [], "Лишний запрос в базу на каждой карточке не нужен."


def test_card_is_never_rendered_without_preparation():
    """Единственная точка отрисовки — та, что сначала дочитывает поля.

    Если карточку начнут собирать где-то ещё, ошибка вернётся: она проявляется
    не всегда, а только после сохранения, и выглядит как случайный сбой.
    """
    source = (ROOT / "bot" / "routers" / "admin" / "crud_admin.py").read_text(encoding="utf-8")
    assert source.count("render_detail(") == 1, (
        "Карточка записи собирается больше чем в одном месте. Отрисовка должна "
        "идти только через _detail_view — он дочитывает поля, которые проставила "
        "база, иначе обработчик упадёт с MissingGreenlet."
    )
    detail_view = source.split("async def _detail_view", 1)[1].split("\nasync def ", 1)[0]
    assert "load_all_fields" in detail_view, (
        "_detail_view перестал дочитывать поля перед отрисовкой — вернётся "
        "падение после сохранения записи."
    )
