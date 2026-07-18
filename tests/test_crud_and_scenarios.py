"""Разбор значений CRUD-панели и шаблоны сценариев."""

from datetime import date

import pytest
import sqlalchemy as sa

from bot.db.models import University, User
from bot.enums import UserRole
from bot.services import crud_service, scenario_service


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
