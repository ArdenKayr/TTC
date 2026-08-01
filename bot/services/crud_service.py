"""CRUD-панель: прямой доступ суперадминов и владельца к таблицам БД.

Каждая таблица описана TableSpec: короткий код (влезает в callback_data),
модель SQLAlchemy и ярлык записи для списка. Владелец видит все таблицы,
суперадмины — только разрешённые; users для суперадминов только на чтение
(роли меняются через панель «Пользователи», где работает иерархия).
Каждое изменение через CRUD пишется в audit_log.

Удалить можно любую запись. База для этого настроена так, что ссылки на
удалённую запись обнуляются, а не запрещают удаление (миграция 0011), —
поэтому вместо тупика «нельзя, есть связи» панель показывает, что именно
связано с записью, и оставляет решение за человеком. Разбор связей строится
автоматически из описания таблиц; руками написаны только их человеческие
названия в LINK_LABELS.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from html import escape
from typing import Any, Callable

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import (
    Activity,
    ActivityRequest,
    AliasSuggestion,
    AuditLog,
    ContentBlock,
    ErrorLog,
    PermissionGroup,
    RegistrationRequest,
    University,
    UniversityAlias,
    UniversityRequest,
    User,
    VoteRequest,
)
from bot.enums import UserRole

PAGE_SIZE = 8
_VALUE_LIMIT = 300  # сколько символов значения показывать в карточке записи


@dataclass(frozen=True)
class TableSpec:
    code: str
    title: str
    model: type
    label: Callable[[Any], str]
    superadmin: bool = True  # видна ли суперадминам (иначе только владельцу)
    write_owner_only: bool = False  # менять может только владелец (users, логи)
    create_fields: tuple[str, ...] = ()  # поля для «Создать запись» (пусто = нельзя)


def _short(text: str | None, limit: int = 35) -> str:
    text = (text or "").strip() or "—"
    return text if len(text) <= limit else text[: limit - 1] + "…"


_SPECS = [
    TableSpec(
        "u",
        "Пользователи",
        User,
        lambda o: f"{_short(o.display_name, 25)} · {o.current_role.value}",
        write_owner_only=True,
    ),
    TableSpec("uni", "Вузы", University, lambda o: _short(o.canonical_name),
              create_fields=("canonical_name", "city")),
    TableSpec(
        "ual",
        "Варианты поиска вузов",
        UniversityAlias,
        lambda o: _short(o.alias_text),
        create_fields=("university_id", "alias_text"),
    ),
    TableSpec(
        "reg",
        "Заявки на регистрацию",
        RegistrationRequest,
        lambda o: f"{_short(o.full_name, 25)} · {o.status.value}",
    ),
    TableSpec(
        "unir",
        "Заявки на вузы",
        UniversityRequest,
        lambda o: f"{_short(o.name, 25)} · {o.status.value}",
    ),
    TableSpec(
        "als",
        "Предложения вариантов",
        AliasSuggestion,
        lambda o: f"{_short(o.alias_text, 25)} · {o.status.value}",
    ),
    TableSpec(
        "actr",
        "Заявки на мероприятия",
        ActivityRequest,
        lambda o: f"{_short(o.title, 25)} · {o.status.value}",
    ),
    TableSpec(
        "act",
        "Мероприятия",
        Activity,
        lambda o: f"{_short(o.title, 25)} · {o.status.value}",
    ),
    TableSpec(
        "vote",
        "Заявки на голосования",
        VoteRequest,
        lambda o: f"{_short(o.question, 25)} · {o.status.value}",
    ),
    TableSpec(
        "perm", "Группы прав", PermissionGroup, lambda o: _short(o.name), superadmin=False
    ),
    TableSpec(
        "cont", "Контент и сценарии", ContentBlock, lambda o: _short(o.slot), superadmin=False
    ),
    # Логи бот сам только пополняет. Правит и чистит их вручную владелец —
    # он же единственный, кто их видит.
    TableSpec(
        "aud",
        "Аудит-лог",
        AuditLog,
        lambda o: f"{o.log_id} · {_short(o.action_type, 25)}",
        superadmin=False,
        write_owner_only=True,
    ),
    TableSpec(
        "err",
        "Логи ошибок",
        ErrorLog,
        lambda o: f"{o.id} · {_short(o.exception_type, 25)}",
        superadmin=False,
        write_owner_only=True,
    ),
]
TABLES: dict[str, TableSpec] = {s.code: s for s in _SPECS}


def specs_for(user: User) -> list[TableSpec]:
    is_owner = user.current_role == UserRole.OWNER
    return [s for s in _SPECS if is_owner or s.superadmin]


def can_view(user: User, spec: TableSpec) -> bool:
    return user.current_role == UserRole.OWNER or spec.superadmin


def can_write(user: User, spec: TableSpec) -> bool:
    if spec.write_owner_only and user.current_role != UserRole.OWNER:
        return False
    return can_view(user, spec)


def columns(spec: TableSpec) -> list[sa.Column]:
    return list(sa.inspect(spec.model).columns)


def pk_col(spec: TableSpec) -> sa.Column:
    return sa.inspect(spec.model).primary_key[0]


def parse_pk(spec: TableSpec, raw: str) -> Any:
    pt = pk_col(spec).type.python_type
    if pt is int:
        return int(raw)
    if pt is uuid.UUID:
        return uuid.UUID(raw)
    return raw


async def count(session: AsyncSession, spec: TableSpec) -> int:
    return await session.scalar(select(func.count()).select_from(spec.model)) or 0


async def page_rows(session: AsyncSession, spec: TableSpec, page: int) -> list[Any]:
    result = await session.scalars(
        select(spec.model)
        .order_by(pk_col(spec).desc())
        .offset(page * PAGE_SIZE)
        .limit(PAGE_SIZE)
    )
    return list(result)


async def get_row(session: AsyncSession, spec: TableSpec, raw_pk: str) -> Any | None:
    try:
        pk = parse_pk(spec, raw_pk)
    except (ValueError, TypeError):
        return None
    return await session.get(spec.model, pk)


def fmt_value(value: Any, limit: int = _VALUE_LIMIT) -> str:
    """Значение поля для показа в карточке (уже экранировано)."""
    if value is None:
        return "—"
    if isinstance(value, Enum):
        return escape(value.value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    text = str(value)
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return escape(text)


def value_hint(col: sa.Column) -> str:
    """Подсказка о формате значения для ввода."""
    try:
        pt = col.type.python_type
    except NotImplementedError:
        pt = str
    if issubclass(pt, Enum):
        allowed = ", ".join(m.value for m in pt)
        hint = f"Одно из: {allowed}."
    elif pt is bool:
        hint = "Логическое: да/нет (true/false, 1/0)."
    elif pt is int:
        hint = "Целое число."
    elif pt is uuid.UUID:
        hint = "UUID."
    elif pt is date:
        hint = "Дата в формате ДД.ММ.ГГГГ."
    elif pt is datetime:
        hint = "Дата-время: ДД.ММ.ГГГГ ЧЧ:ММ (или ISO)."
    elif pt in (dict, list):
        hint = "JSON."
    else:
        length = getattr(col.type, "length", None)
        hint = f"Текст до {length} символов." if length else "Текст."
    if col.nullable:
        hint += " «-» — очистить поле."
    return hint


_TRUE = {"1", "true", "да", "yes", "+"}
_FALSE = {"0", "false", "нет", "no"}


def parse_value(col: sa.Column, raw: str) -> Any:
    """Значение из текста админа. ValueError с человеческим объяснением — если не вышло."""
    raw = raw.strip()
    if raw == "-":
        if not col.nullable:
            raise ValueError("это поле нельзя очистить (NOT NULL)")
        return None
    try:
        pt = col.type.python_type
    except NotImplementedError:
        pt = str
    if issubclass(pt, Enum):
        try:
            return pt(raw)
        except ValueError:
            allowed = ", ".join(m.value for m in pt)
            raise ValueError(f"допустимые значения: {allowed}") from None
    if pt is bool:
        low = raw.lower()
        if low in _TRUE:
            return True
        if low in _FALSE:
            return False
        raise ValueError("нужно да/нет (true/false, 1/0)")
    if pt is int:
        try:
            return int(raw)
        except ValueError:
            raise ValueError("нужно целое число") from None
    if pt is uuid.UUID:
        try:
            return uuid.UUID(raw)
        except ValueError:
            raise ValueError("нужен UUID") from None
    if pt is date:
        try:
            return datetime.strptime(raw, "%d.%m.%Y").date()
        except ValueError:
            raise ValueError("нужна дата в формате ДД.ММ.ГГГГ") from None
    if pt is datetime:
        for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y"):
            try:
                return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            raise ValueError("нужна дата-время: ДД.ММ.ГГГГ ЧЧ:ММ или ISO") from None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    if pt in (dict, list):
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"невалидный JSON ({e.msg})") from None
    length = getattr(col.type, "length", None)
    if length and len(raw) > length:
        raise ValueError(f"текст длиннее {length} символов")
    return raw


async def load_all_fields(session: AsyncSession, obj: Any) -> None:
    """Дочитывает поля, значение которых проставила сама база.

    После сохранения SQLAlchemy помечает «непрочитанными» те колонки, которые
    вычислила база: ``updated_at`` с ``onupdate=now()``, ``created_at`` со
    ``server_default``. Значение там уже новое, но коду оно неизвестно.

    Опасно здесь то, что за ним библиотека сходит **незаметно** — прямо в
    момент чтения атрибута (``obj.updated_at``). В асинхронном SQLAlchemy так
    нельзя: скрытый запрос вне ``await`` падает с ``MissingGreenlet``, и
    карточка записи не рисуется вовсе. Поэтому перед показом дочитываем всё
    недостающее явно.

    Список полей берётся у самого объекта, а не из перечня таблиц: появится
    новая колонка со значением от базы — она попадёт сюда сама.
    """
    unloaded = sa.inspect(obj).unloaded
    if unloaded:
        await session.refresh(obj, list(unloaded))


def render_detail(spec: TableSpec, obj: Any, header: str) -> str:
    from bot import texts  # локально: texts импортирует enums, а не наоборот

    lines = [header]
    for col in columns(spec):
        lines.append(
            texts.CRUD_ROW_FIELD.format(name=col.name, value=fmt_value(getattr(obj, col.key)))
        )
    text = "\n".join(lines)
    return text if len(text) <= 4000 else text[:3999] + "…"


# --------------------------------------------------------------------------
# Что связано с записью
# --------------------------------------------------------------------------

# Как назвать записи, которые ссылаются на удаляемую. Ключ — таблица и колонка
# со ссылкой. Значение — три формы существительного (1 / 2 / 5) и пояснение,
# чем эта запись приходится удаляемой.
#
# Сам список ссылок вычисляется из описания таблиц, поэтому забыть здесь новую
# связь нельзя: за этим следит tests/test_crud_links.py.
LINK_LABELS: dict[tuple[str, str], tuple[tuple[str, str, str], str]] = {
    # Ссылки на человека
    ("activity_requests", "tg_id"): (
        ("заявка на мероприятие", "заявки на мероприятие", "заявок на мероприятие"),
        "он подал",
    ),
    ("activity_requests", "processed_by"): (
        ("заявка на мероприятие", "заявки на мероприятие", "заявок на мероприятие"),
        "он разобрал",
    ),
    ("activities", "organizer_id"): (
        ("мероприятие", "мероприятия", "мероприятий"),
        "он организатор",
    ),
    ("vote_requests", "tg_id"): (
        ("заявка на голосование", "заявки на голосование", "заявок на голосование"),
        "он подал",
    ),
    ("vote_requests", "processed_by"): (
        ("заявка на голосование", "заявки на голосование", "заявок на голосование"),
        "он разобрал",
    ),
    ("registration_requests", "processed_by"): (
        ("заявка на регистрацию", "заявки на регистрацию", "заявок на регистрацию"),
        "он разобрал",
    ),
    ("university_requests", "processed_by"): (
        ("заявка на вуз", "заявки на вуз", "заявок на вуз"),
        "он разобрал",
    ),
    ("alias_suggestions", "processed_by"): (
        ("предложение варианта", "предложения варианта", "предложений варианта"),
        "он разобрал",
    ),
    ("audit_log", "actor_tg_id"): (
        ("запись аудита", "записи аудита", "записей аудита"),
        "это его действия",
    ),
    ("content_blocks", "updated_by"): (
        ("блок контента", "блока контента", "блоков контента"),
        "он менял последним",
    ),
    # Ссылки на вуз
    ("users", "university_id"): (
        ("участник", "участника", "участников"),
        "у них указан этот вуз",
    ),
    ("registration_requests", "university_id"): (
        ("заявка на регистрацию", "заявки на регистрацию", "заявок на регистрацию"),
        "в них указан этот вуз",
    ),
    ("university_requests", "created_university_id"): (
        ("заявка на вуз", "заявки на вуз", "заявок на вуз"),
        "по ним вуз и создан",
    ),
    ("university_aliases", "university_id"): (
        ("вариант поиска", "варианта поиска", "вариантов поиска"),
        "",
    ),
    ("alias_suggestions", "university_id"): (
        ("предложение варианта", "предложения варианта", "предложений варианта"),
        "",
    ),
    # Прочие ссылки
    ("activities", "request_id"): (
        ("мероприятие", "мероприятия", "мероприятий"),
        "создано по этой заявке",
    ),
    ("registration_requests", "university_request_id"): (
        ("заявка на регистрацию", "заявки на регистрацию", "заявок на регистрацию"),
        "ждёт решения по этой заявке на вуз",
    ),
    ("users", "permission_group_id"): (
        ("участник", "участника", "участников"),
        "состоят в этой группе прав",
    ),
}


# Ссылки «по номеру», без жёсткой связи в базе. Заявку человек подаёт до того,
# как у него появляется запись в users, поэтому связать их было нельзя. При
# удалении человека такие записи остаются с номером несуществующего аккаунта —
# и предупреждение обязано об этом сказать, иначе оно вводит в заблуждение.
SOFT_LINKS: dict[tuple[str, str], tuple[str, tuple[str, str, str], str]] = {
    ("registration_requests", "tg_id"): (
        "users",
        ("заявка на регистрацию", "заявки на регистрацию", "заявок на регистрацию"),
        "он подал",
    ),
    ("university_requests", "tg_id"): (
        "users",
        ("заявка на вуз", "заявки на вуз", "заявок на вуз"),
        "он подал",
    ),
    ("alias_suggestions", "tg_id"): (
        "users",
        ("предложение варианта", "предложения варианта", "предложений варианта"),
        "он предложил",
    ),
    ("audit_log", "target_tg_id"): (
        "users",
        ("запись аудита", "записи аудита", "записей аудита"),
        "он в них тот, кого касалось действие",
    ),
    ("error_log", "user_tg_id"): (
        "users",
        ("запись об ошибке", "записи об ошибке", "записей об ошибке"),
        "сбой случился у него",
    ),
}

# Что станет со связанными записями после удаления.
CLEARED = "cleared"  # запись останется, ссылка опустеет
KEPT = "kept"  # запись останется, и в ней останется номер удалённого
CASCADED = "cascaded"  # запись удалится вместе с этой


@dataclass(frozen=True)
class RelatedGroup:
    """Одна пачка записей, которые ссылаются на удаляемую."""

    count: int
    noun: str  # «11 мероприятий» — уже в нужной форме
    role: str  # «он организатор»
    fate: str  # CLEARED / KEPT / CASCADED


def plural(n: int, one: str, few: str, many: str) -> str:
    """Форма существительного при числе: 1 заявка, 2 заявки, 5 заявок."""
    if n % 100 // 10 == 1:
        return many
    last = n % 10
    if last == 1:
        return one
    if 2 <= last <= 4:
        return few
    return many


def incoming_links(table: sa.Table) -> list[tuple[sa.Table, sa.Column, Any]]:
    """Все ссылки на эту таблицу: (откуда, какая колонка, сама связь)."""
    from bot.db.base import Base

    found = []
    for other in Base.metadata.tables.values():
        for fk in sorted(other.foreign_keys, key=lambda f: f.parent.name):
            if fk.column.table is table:
                found.append((other, fk.parent, fk))
    return found


async def related(session: AsyncSession, spec: TableSpec, obj: Any) -> list[RelatedGroup]:
    """Что ссылается на запись — с количеством и человеческим объяснением.

    Считаются только прямые ссылки: в этой базе у записей, удаляемых вместе с
    родителем (варианты поиска вуза, предложения вариантов), своих потомков
    нет, поэтому глубже спускаться незачем.
    """
    from bot.db.base import Base

    table = spec.model.__table__
    pk = pk_col(spec)
    pk_value = getattr(obj, pk.key)

    async def measure(child: sa.Table, column: sa.Column) -> int:
        return await session.scalar(
            select(func.count()).select_from(child).where(column == pk_value)
        )

    groups: list[RelatedGroup] = []
    for child, column, fk in incoming_links(table):
        if fk.column.name != pk.name:
            continue
        found = await measure(child, column)
        if not found:
            continue
        forms, role = LINK_LABELS.get(
            (child.name, column.name), ((child.name, child.name, child.name), "")
        )
        groups.append(
            RelatedGroup(
                count=found,
                noun=plural(found, *forms),
                role=role,
                fate=CASCADED if (fk.ondelete or "").upper() == "CASCADE" else CLEARED,
            )
        )

    for (child_name, column_name), (target, forms, role) in SOFT_LINKS.items():
        if target != table.name:
            continue
        child = Base.metadata.tables[child_name]
        found = await measure(child, child.columns[column_name])
        if not found:
            continue
        groups.append(
            RelatedGroup(count=found, noun=plural(found, *forms), role=role, fate=KEPT)
        )

    groups.sort(key=lambda g: (-g.count, g.noun))
    return groups


def describe_links(groups: list[RelatedGroup]) -> str:
    """Связи словами — для экрана подтверждения удаления."""
    from bot import texts

    if not groups:
        return texts.CRUD_LINKS_NONE

    def line(group: RelatedGroup) -> str:
        tail = f" — {group.role}" if group.role else ""
        return texts.CRUD_LINKS_ITEM.format(count=group.count, noun=group.noun, role=tail)

    sections = [
        (CLEARED, texts.CRUD_LINKS_CLEARED),
        (KEPT, texts.CRUD_LINKS_KEPT),
        (CASCADED, texts.CRUD_LINKS_GONE),
    ]
    parts = []
    for fate, template in sections:
        rows = [g for g in groups if g.fate == fate]
        if rows:
            parts.append(template.format(items="\n".join(line(g) for g in rows)))
    return "\n\n".join(parts)


def audit_value(value: Any) -> str | None:
    """Значение для меты аудита: короткая строка или None."""
    if value is None:
        return None
    if isinstance(value, Enum):
        return value.value
    return str(value)[:200]
