"""Сторож «Карты сценариев».

Смысл этих тестов — сделать так, чтобы карта в docs/scenario-map.json физически
не могла отстать от кода. Добавили команду или кнопку и не описали её на карте —
падает тест. Удалили из кода то, что на карте описано, — тоже падает.

Именно поэтому карте можно доверять: её актуальность держится на проверке,
а не на том, что кто-то не забыл её обновить.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_scenario_map import SPEC_PATH, SpecError, collect_code_facts, resolve_trigger

ROOT = Path(__file__).resolve().parent.parent

# Роли, которыми можно помечать узлы карты. «guest» и «any» — не значения
# UserRole, а состояния «ещё не зарегистрирован» и «доступно всем».
EXTRA_ROLES = {"guest", "any"}


@pytest.fixture(scope="module")
def spec() -> dict:
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def facts():
    return collect_code_facts()


@pytest.fixture(scope="module")
def nodes(spec: dict) -> list[dict]:
    return [node for area in spec["areas"] for node in area["nodes"]]


# --------------------------------------------------------------------------
# Целостность самой карты
# --------------------------------------------------------------------------


def test_node_ids_unique(nodes: list[dict]) -> None:
    ids = [node["id"] for node in nodes]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    assert not duplicates, f"Повторяющиеся id узлов карты: {duplicates}"


def test_next_targets_exist(nodes: list[dict]) -> None:
    known = {node["id"] for node in nodes}
    broken = [
        (node["id"], target)
        for node in nodes
        for target in node.get("next", [])
        if target not in known
    ]
    assert not broken, f"Ссылки «Дальше» ведут в никуда: {broken}"


def test_every_node_is_described(nodes: list[dict]) -> None:
    """У каждой точки входа должно быть сказано, что она делает и что видно."""
    empty = [n["id"] for n in nodes if not n.get("does") or not n.get("shows")]
    assert not empty, f"Узлы без описания «делает» или «человек видит»: {empty}"


def test_roles_are_real(nodes: list[dict], facts) -> None:
    allowed = set(facts.roles) | EXTRA_ROLES
    unknown = sorted(
        {role for node in nodes for role in node.get("roles", []) if role not in allowed}
    )
    assert not unknown, f"На карте указаны несуществующие роли: {unknown}"


# --------------------------------------------------------------------------
# Карта не отстаёт от кода
# --------------------------------------------------------------------------


def test_all_commands_are_on_the_map(nodes: list[dict], facts) -> None:
    mapped: set[str] = set()
    for node in nodes:
        if node.get("trigger_kind") == "command":
            mapped.add(node.get("trigger_text", "").lstrip("/").split()[0])
        mapped.update(node.get("covers_commands", []))

    missing = sorted(set(facts.commands) - mapped)
    assert not missing, (
        "В коде есть команды, которых нет на карте сценариев: "
        + ", ".join(f"/{c} ({facts.commands[c]})" for c in missing)
        + ". Опишите их в docs/scenario-map.json."
    )

    extra = sorted(mapped - set(facts.commands) - {""})
    assert not extra, f"На карте описаны команды, которых больше нет в коде: {extra}"


def test_all_buttons_are_on_the_map(nodes: list[dict], spec: dict, facts) -> None:
    mapped: set[str] = set()
    for node in nodes:
        if node.get("trigger_ref"):
            mapped.add(node["trigger_ref"])
        mapped.update(node.get("covers_buttons", []))

    ignored = set(spec.get("ignored_buttons", {}))
    missing = sorted(set(facts.buttons) - mapped - ignored)
    assert not missing, (
        "В bot/texts.py есть кнопки, которых нет на карте: "
        + ", ".join(f"{ref} = «{facts.buttons[ref]}»" for ref in missing)
        + ". Опишите их в docs/scenario-map.json либо внесите в ignored_buttons "
        "с пояснением, почему это не точка входа."
    )

    stale = sorted((mapped | ignored) - set(facts.buttons))
    assert not stale, f"Карта ссылается на кнопки, которых больше нет в texts.py: {stale}"


def test_trigger_refs_resolve(nodes: list[dict], facts) -> None:
    for node in nodes:
        try:
            assert resolve_trigger(node, facts)
        except SpecError as exc:  # pragma: no cover — сообщение важнее трассировки
            pytest.fail(str(exc))


def test_permission_modules_covered(nodes: list[dict], facts) -> None:
    used = {node["perm_module"] for node in nodes if node.get("perm_module")}
    missing = sorted(set(facts.modules) - used)
    assert not missing, (
        f"Модули прав, не встречающиеся на карте: {missing}. "
        "Значит, непонятно, что именно они открывают."
    )
    stale = sorted(used - set(facts.modules))
    assert not stale, f"На карте есть модули прав, которых нет в коде: {stale}"


def _check_registry(entries: list[dict], real: dict[str, str], known_ids: set[str], what: str) -> None:
    keys = {entry["key"] for entry in entries}

    missing = sorted(set(real) - keys)
    assert not missing, f"{what}, которых нет на карте: {missing}"

    stale = sorted(keys - set(real))
    assert not stale, f"На карте есть {what.lower()}, которых нет в коде: {stale}"

    orphans = sorted(entry["key"] for entry in entries if not entry.get("nodes"))
    assert not orphans, (
        f"{what} без привязки к точке карты: {orphans}. "
        "Непонятно, в какой момент человек это видит."
    )

    broken = [
        (entry["key"], node_id)
        for entry in entries
        for node_id in entry.get("nodes", [])
        if node_id not in known_ids
    ]
    assert not broken, f"{what} ссылаются на несуществующие узлы: {broken}"


def test_content_slots_covered(spec: dict, nodes: list[dict], facts) -> None:
    known = {node["id"] for node in nodes}
    _check_registry(spec.get("slots", []), facts.slots, known, "Редактируемые блоки /content")


def test_scenarios_covered(spec: dict, nodes: list[dict], facts) -> None:
    known = {node["id"] for node in nodes}
    _check_registry(spec.get("scenarios", []), facts.scenarios, known, "Редактируемые сценарии")


def test_database_tables_match(spec: dict, nodes: list[dict], facts) -> None:
    described = {table["name"] for table in spec.get("tables", [])}
    real = set(facts.db_tables) - {"alembic_version"}

    missing = sorted(real - described)
    assert not missing, f"Таблицы базы, не описанные на карте: {missing}"

    stale = sorted(described - real)
    assert not stale, f"На карте описаны таблицы, которых нет в базе: {stale}"

    mentioned = {
        name
        for node in nodes
        for name in node.get("db_reads", []) + node.get("db_writes", [])
    }
    unknown = sorted(mentioned - real)
    assert not unknown, f"Узлы карты ссылаются на несуществующие таблицы: {unknown}"


# --------------------------------------------------------------------------
# Сборка карты работает
# --------------------------------------------------------------------------


def test_map_builds(spec: dict, facts) -> None:
    from scripts.build_scenario_map import render_html

    page = render_html(spec, facts)
    assert page.startswith("<!doctype html>")
    assert "карта сценариев" in page.lower()


def test_role_buttons_are_not_confused_with_tools(spec: dict, facts) -> None:
    """Кнопки выбора роли ищутся на странице по классу «f».

    Однажды этот класс достался кнопкам «Свернуть ветки» и «Показать
    возвраты» — и нажатие на них выставляло роль в «ничто», после чего схема
    показывала почти пустоту. Проверяем, что по этому селектору не попадает
    ничего лишнего.
    """
    import re

    from scripts.build_scenario_map import render_html

    page = render_html(spec, facts)
    strays = [
        tag
        for tag in re.findall(r"<button[^>]*>", page)
        if re.search(r'class="[^"]*\bf\b[^"]*"', tag) and "data-role=" not in tag
    ]
    assert not strays, (
        "У этих кнопок класс «f», но не задана роль — они попадут в фильтр ролей "
        f"и сломают его: {strays}"
    )


def test_graph_shows_every_node(spec: dict, nodes: list[dict], facts) -> None:
    """Визуальная схема должна показывать всю карту, а не её часть.

    Схема рисуется в браузере по данным, вшитым в страницу. Если при правке
    генератора часть узлов перестанет туда попадать, на схеме молча исчезнут
    целые ветки — заметить это глазами почти невозможно, поэтому проверяем.
    """
    from scripts.build_scenario_map import _graph_payload

    payload = _graph_payload(spec, facts)
    assert "</" not in payload, (
        "В данных схемы есть последовательность «</» — она закроет тег <script> "
        "раньше времени и страница сломается."
    )

    data = json.loads(payload.replace("<\\/", "</"))
    drawn = [node for area in data["areas"] for node in area["nodes"]]

    assert {n["id"] for n in drawn} == {n["id"] for n in nodes}, (
        "Набор узлов на схеме разошёлся со списком карты."
    )

    nameless = [n["id"] for n in drawn if not n.get("t")]
    assert not nameless, f"Узлы схемы без подписи: {nameless}"

    known = {n["id"] for n in drawn}
    dangling = [(n["id"], t) for n in drawn for t in n["n"] if t not in known]
    assert not dangling, f"Стрелки схемы ведут в никуда: {dangling}"
