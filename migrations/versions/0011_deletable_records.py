"""удаление любой записи: ссылки обнуляются вместо запрета

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-02

Раньше база запрещала удалить запись, на которую кто-то ссылается: у связей
не было правила на удаление, а три ссылки были ещё и обязательными. Из-за
этого владелец не мог убрать из базы человека, если тот когда-либо подавал
заявку.

Теперь ссылки на людей и справочники при удалении обнуляются: сама запись
остаётся (заявка, мероприятие, строка аудита), но автор в ней становится
пустым — «удалённый пользователь». Двум связям оставлено удаление вместе с
родителем: вариант поиска вуза и предложение варианта без своего вуза
смысла не имеют.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (таблица, колонка, куда ведёт, колонка назначения, имя связи)
# Имя нужно задать явно: две связи в моделях названы не по общему шаблону,
# и после миграции имена должны совпасть с тем, что объявлено в коде.
_LINKS = [
    ("activity_requests", "tg_id", "users", "tg_id", None),
    ("activity_requests", "processed_by", "users", "tg_id", None),
    ("activities", "organizer_id", "users", "tg_id", None),
    ("activities", "request_id", "activity_requests", "request_id", None),
    ("vote_requests", "tg_id", "users", "tg_id", None),
    ("vote_requests", "processed_by", "users", "tg_id", None),
    ("audit_log", "actor_tg_id", "users", "tg_id", None),
    ("content_blocks", "updated_by", "users", "tg_id", None),
    ("registration_requests", "university_id", "universities", "university_id", None),
    (
        "registration_requests",
        "university_request_id",
        "university_requests",
        "request_id",
        "fk_reg_requests_university_request",
    ),
    ("registration_requests", "processed_by", "users", "tg_id", None),
    ("university_requests", "processed_by", "users", "tg_id", None),
    (
        "university_requests",
        "created_university_id",
        "universities",
        "university_id",
        None,
    ),
    ("alias_suggestions", "processed_by", "users", "tg_id", None),
    ("users", "university_id", "universities", "university_id", None),
    ("users", "permission_group_id", "permission_groups", "group_id", "fk_users_permission_group"),
]

# Ссылки, которые были обязательными: обнулить их нельзя, пока стоит NOT NULL.
_MADE_OPTIONAL = [
    ("activity_requests", "tg_id", sa.BigInteger()),
    ("activities", "organizer_id", sa.BigInteger()),
    ("vote_requests", "tg_id", sa.BigInteger()),
]


def _existing_fk(conn, table: str, column: str) -> str | None:
    """Имя связи по колонке — каким бы оно ни было.

    Часть связей создавалась разными миграциями, и полагаться на шаблон имени
    нельзя: не найдя связь по имени, миграция упала бы посреди накатки на
    боевой базе. Поэтому имя спрашиваем у самого PostgreSQL.
    """
    return conn.execute(
        sa.text(
            """
            SELECT con.conname
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            JOIN pg_namespace ns ON ns.oid = rel.relnamespace
            JOIN pg_attribute att
              ON att.attrelid = rel.oid AND att.attnum = con.conkey[1]
            WHERE con.contype = 'f'
              AND array_length(con.conkey, 1) = 1
              AND rel.relname = :table
              AND att.attname = :column
              AND ns.nspname = current_schema()
            """
        ),
        {"table": table, "column": column},
    ).scalar()


def _relink(ondelete: str | None) -> None:
    conn = op.get_bind()
    for table, column, ref_table, ref_column, name in _LINKS:
        old = _existing_fk(conn, table, column)
        if old:
            op.drop_constraint(old, table, type_="foreignkey")
        op.create_foreign_key(
            name or f"fk_{table}_{column}_{ref_table}",
            table,
            ref_table,
            [column],
            [ref_column],
            ondelete=ondelete,
        )


def upgrade() -> None:
    for table, column, kind in _MADE_OPTIONAL:
        op.alter_column(table, column, existing_type=kind, nullable=True)
    _relink("SET NULL")


def downgrade() -> None:
    conn = op.get_bind()
    # Вернуть NOT NULL можно только если ни у одной записи автор не потерян:
    # иначе откат оборвётся на середине и оставит базу в непонятном виде.
    for table, column, _kind in _MADE_OPTIONAL:
        orphans = conn.execute(
            sa.text(f"SELECT count(*) FROM {table} WHERE {column} IS NULL")
        ).scalar()
        if orphans:
            raise RuntimeError(
                f"Откат невозможен: в таблице {table} у {orphans} записей пустое поле "
                f"{column} (их авторы удалены). Заполните его или удалите эти записи."
            )
    _relink(None)
    for table, column, kind in _MADE_OPTIONAL:
        op.alter_column(table, column, existing_type=kind, nullable=False)
