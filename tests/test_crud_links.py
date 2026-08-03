"""Сторож удаления записей через CRUD.

Владелец должен иметь возможность удалить любую запись базы. Это держится на
двух свойствах схемы, которые легко сломать случайной правкой модели:

* у каждой связи задано, что делать при удалении родителя — иначе PostgreSQL
  просто откажет, и в панели снова появится тупик «нельзя, есть связи»;
* ссылка, которая при удалении обнуляется, не может быть обязательной —
  иначе обнуление упрётся в NOT NULL.

Плюс проверяем, что у каждой связи есть человеческое название: без него
предупреждение перед удалением показало бы техническое имя таблицы.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from bot.db.base import Base

# Импорт моделей регистрирует все таблицы в Base.metadata — без него проверять
# было бы нечего.
from bot.db.models import University, User
from bot.enums import UserRole
from bot.services import crud_service


class _CountingSession:
    """Подставная база: запоминает вопросы и на каждый отвечает одним числом."""

    def __init__(self, answer: int = 3) -> None:
        self.answer = answer
        self.asked: list[str] = []

    async def scalar(self, statement) -> int:
        self.asked.append(str(statement.compile(compile_kwargs={"literal_binds": True})))
        return self.answer


def _all_links():
    """Все связи базы: (таблица, колонка, сама связь)."""
    for table in Base.metadata.tables.values():
        for fk in table.foreign_keys:
            yield table, fk.parent, fk


def test_every_link_has_a_delete_rule() -> None:
    naked = [
        f"{table.name}.{column.name} → {fk.column.table.name}"
        for table, column, fk in _all_links()
        if not fk.ondelete
    ]
    assert not naked, (
        "У этих связей не задано, что делать при удалении родителя — "
        f"база запретит удаление: {naked}. Добавьте ondelete=\"SET NULL\" "
        "(запись останется, ссылка опустеет) или \"CASCADE\" (удалится вместе)."
    )


def test_nullable_where_link_is_cleared() -> None:
    """SET NULL на обязательной колонке — это отказ базы во время удаления."""
    broken = [
        f"{table.name}.{column.name}"
        for table, column, fk in _all_links()
        if (fk.ondelete or "").upper() == "SET NULL" and not column.nullable
    ]
    assert not broken, (
        "Эти ссылки при удалении обнуляются, но колонка обязательная — "
        f"удаление упадёт: {broken}. Сделайте поле необязательным."
    )


def test_every_link_has_a_human_name() -> None:
    missing = [
        (table.name, column.name)
        for table, column, _fk in _all_links()
        if (table.name, column.name) not in crud_service.LINK_LABELS
    ]
    assert not missing, (
        f"Связи без человеческого названия: {missing}. Допишите их в "
        "crud_service.LINK_LABELS — иначе перед удалением человек увидит "
        "техническое имя таблицы вместо объяснения."
    )


def test_no_stale_link_names() -> None:
    real = {(table.name, column.name) for table, column, _fk in _all_links()}
    stale = sorted(set(crud_service.LINK_LABELS) - real)
    assert not stale, f"В LINK_LABELS описаны связи, которых больше нет в базе: {stale}"


def test_link_names_have_three_forms() -> None:
    broken = [
        key for key, (forms, _role) in crud_service.LINK_LABELS.items() if len(forms) != 3
    ]
    assert not broken, f"Нужны три формы существительного (1/2/5): {broken}"


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        (1, "заявка"),
        (2, "заявки"),
        (4, "заявки"),
        (5, "заявок"),
        (11, "заявок"),
        (12, "заявок"),
        (21, "заявка"),
        (22, "заявки"),
        (25, "заявок"),
        (111, "заявок"),
        (121, "заявка"),
    ],
)
def test_plural(number: int, expected: str) -> None:
    assert crud_service.plural(number, "заявка", "заявки", "заявок") == expected


def test_owner_can_change_every_table() -> None:
    """Ни одной таблицы, закрытой от владельца на изменение, быть не должно."""
    owner = User(tg_id=1, display_name="Владелец", current_role=UserRole.OWNER)
    closed = [
        spec.title for spec in crud_service.TABLES.values() if not crud_service.can_write(owner, spec)
    ]
    assert not closed, f"Владелец не может править эти таблицы: {closed}"


def test_describe_links_splits_by_what_happens_next() -> None:
    text = crud_service.describe_links(
        [
            crud_service.RelatedGroup(11, "мероприятий", "он организатор", crud_service.CLEARED),
            crud_service.RelatedGroup(
                7, "заявок на регистрацию", "он подал", crud_service.KEPT
            ),
            crud_service.RelatedGroup(5, "вариантов поиска", "", crud_service.CASCADED),
        ]
    )
    assert "11 мероприятий — он организатор" in text
    assert "7 заявок на регистрацию — он подал" in text
    assert "5 вариантов поиска" in text
    # Три исхода должны идти отдельными блоками и в понятном порядке:
    # что опустеет, что останется с номером, что исчезнет совсем.
    assert text.index("11 мероприятий") < text.index("7 заявок") < text.index("5 вариантов")
    assert "опустеет" in text
    assert "номером человека" in text
    assert "вместе" in text


def test_soft_links_point_at_real_columns() -> None:
    """Ссылки «по номеру» описаны вручную — колонки должны существовать."""
    for (table_name, column_name), (target, _forms, _role) in crud_service.SOFT_LINKS.items():
        table = Base.metadata.tables.get(table_name)
        assert table is not None, f"В базе нет таблицы {table_name}"
        assert column_name in table.columns, f"В {table_name} нет колонки {column_name}"
        assert target in Base.metadata.tables, f"В базе нет таблицы {target}"
        assert (table_name, column_name) not in {
            (t.name, c.name) for t, c, _ in _all_links()
        }, (
            f"{table_name}.{column_name} — настоящая связь, а не ссылка по номеру. "
            "Уберите её из SOFT_LINKS: иначе она посчитается дважды."
        )


def test_account_number_columns_are_all_described() -> None:
    """Новая колонка с номером аккаунта не должна пропасть из предупреждения.

    Такие колонки хранят tg_id, но связью не оформлены (человек подаёт заявку
    раньше, чем у него появляется запись в users). При удалении человека они
    остаются с номером несуществующего аккаунта — и он должен об этом узнать.
    """
    hard = {(t.name, c.name) for t, c, _ in _all_links()}
    suspects = {
        (table.name, column.name)
        for table in Base.metadata.tables.values()
        for column in table.columns
        if column.name.endswith("tg_id") and table.name != "users"
    }
    forgotten = sorted(suspects - hard - set(crud_service.SOFT_LINKS))
    assert not forgotten, (
        f"Колонки с номером аккаунта, не описанные нигде: {forgotten}. "
        "Добавьте их в crud_service.SOFT_LINKS — иначе перед удалением человека "
        "владелец о них не узнает."
    )


def test_describe_links_when_nothing_points_here() -> None:
    assert "ничто не ссылается" in crud_service.describe_links([])


def test_related_asks_about_every_link_to_a_person() -> None:
    """Полный путь «нажали Удалить» — без базы, но с настоящими запросами."""
    session = _CountingSession()
    person = User(tg_id=42, display_name="Тест", current_role=UserRole.USER)
    groups = asyncio.run(crud_service.related(session, crud_service.TABLES["u"], person))

    hard = {(t.name, c.name) for t, c, fk in _all_links() if fk.column.table.name == "users"}
    soft = {key for key, (target, *_) in crud_service.SOFT_LINKS.items() if target == "users"}
    assert len(groups) == len(hard) + len(soft), (
        "Посчитаны не все ссылки на человека: "
        f"спросили про {len(groups)}, а их {len(hard) + len(soft)}"
    )
    assert all("42" in question for question in session.asked), (
        "Какой-то запрос ищет не по номеру удаляемого аккаунта"
    )
    for table, column in hard | soft:
        assert any(table in q and column in q for q in session.asked), (
            f"Про {table}.{column} база не спрошена"
        )

    cleared = [g for g in groups if g.fate == crud_service.CLEARED]
    kept = [g for g in groups if g.fate == crud_service.KEPT]
    assert len(cleared) == len(hard), "Настоящие связи должны обнуляться"
    assert len(kept) == len(soft), "Ссылки по номеру должны остаться как есть"
    assert all(g.count == 3 for g in groups)
    assert not any(g.fate == crud_service.CASCADED for g in groups), (
        "Вместе с человеком ничего удаляться не должно"
    )


def test_related_marks_what_dies_with_a_university() -> None:
    session = _CountingSession()
    uni = University(university_id=7, canonical_name="СПбГУ")
    groups = asyncio.run(crud_service.related(session, crud_service.TABLES["uni"], uni))

    cascaded = {g.noun for g in groups if g.fate == crud_service.CASCADED}
    assert cascaded == {"варианта поиска", "предложения варианта"}, (
        f"Вместе с вузом должны уходить его варианты поиска, а уходит: {cascaded}"
    )
    assert any(g.fate == crud_service.CLEARED for g in groups), (
        "У участников и заявок вуз должен просто опустеть"
    )


def test_related_says_nothing_when_no_one_points_here() -> None:
    session = _CountingSession(answer=0)
    person = User(tg_id=42, display_name="Тест", current_role=UserRole.USER)
    groups = asyncio.run(crud_service.related(session, crud_service.TABLES["u"], person))
    assert groups == []
    assert "ничто не ссылается" in crud_service.describe_links(groups)


_VERSIONS = Path(__file__).resolve().parent.parent / "migrations" / "versions"


def _migration_0011():
    """Миграция, которая перевела связи на обнуление."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "migration_0011", _VERSIONS / "0011_deletable_records.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tables_created_after_0011() -> set[str]:
    """Таблицы, заведённые уже после 0011.

    Такая таблица создаётся сразу с нужным правилом удаления — переделывать
    её 0011 не может и не должна. Считаем их по самим миграциям, а не списком
    в тесте: список пришлось бы пополнять вручную, и он бы отстал.
    """
    created: set[str] = set()
    for path in sorted(_VERSIONS.glob("[0-9]*.py")):
        if path.name[:4] <= "0011":
            continue
        created |= set(
            re.findall(r'create_table\(\s*"([a-z_]+)"', path.read_text(encoding="utf-8"))
        )
    return created


def test_migration_covers_exactly_the_cleared_links() -> None:
    """Список связей в миграции должен совпадать с моделями.

    Разойтись легко: добавили в модель ссылку с обнулением, а миграцию
    поправить забыли — тогда в базе у неё останется старое правило, и
    удаление снова начнёт упираться. Проверяем в обе стороны.
    """
    module = _migration_0011()
    born_later = _tables_created_after_0011()
    in_migration = {(table, column) for table, column, *_ in module._LINKS}
    in_models = {
        (table.name, column.name)
        for table, column, fk in _all_links()
        if (fk.ondelete or "").upper() == "SET NULL" and table.name not in born_later
    }

    forgotten = sorted(in_models - in_migration)
    assert not forgotten, (
        f"В моделях ссылка обнуляется, а миграция её не переделывает: {forgotten}"
    )
    extra = sorted(in_migration - in_models)
    assert not extra, (
        f"Миграция переделывает связи, которых в моделях уже нет или они не обнуляются: {extra}"
    )


def test_migration_makes_the_right_columns_optional() -> None:
    """Обязательными не должны остаться те ссылки, которые обнуляются."""
    module = _migration_0011()
    made_optional = {(table, column) for table, column, _kind in module._MADE_OPTIONAL}
    for table, column in made_optional:
        real = Base.metadata.tables[table].columns[column]
        assert real.nullable, (
            f"Миграция снимает обязательность с {table}.{column}, "
            "а в модели поле осталось обязательным."
        )
