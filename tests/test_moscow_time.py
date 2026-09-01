"""Время в журналах читает человек — значит, оно московское.

Из журнала ошибок на бою, запись №8:

    №8 01.09 17:53 · TelegramNetworkError: Request timeout error

Сбой случился в 20:53 по Петербургу. Сервер живёт по UTC, и в базе так и
надо хранить — но владелец разбирался в поломке, сверяя записи со своими
часами, и три часа разницы сбивали именно там, где важна точность.

Здесь проверяется, что время наружу выходит московским, а рядом с ним
стоит подпись — чтобы не пришлось гадать, какой это пояс.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from bot import texts, timefmt
from bot.routers.admin.owner_panel import _audit_line, _error_line

# Тот самый сбой: 17:53 по UTC — это 20:53 в Петербурге.
CRASH = datetime(2026, 9, 1, 17, 53, 52, tzinfo=timezone.utc)


def test_utc_becomes_moscow() -> None:
    assert timefmt.to_msk(CRASH).hour == 20
    assert timefmt.to_msk(CRASH).utcoffset() == timedelta(hours=3)


def test_time_without_zone_is_read_as_utc() -> None:
    """База может отдать момент без пояса — считать его местным нельзя.

    Иначе время «поедет» на три часа в другую сторону, и запись окажется
    в будущем относительно соседних.
    """
    naive = CRASH.replace(tzinfo=None)
    assert timefmt.short(naive) == timefmt.short(CRASH)


def test_formats_are_readable() -> None:
    assert timefmt.short(CRASH) == "01.09 20:53"
    assert timefmt.full(CRASH) == "01.09.2026 20:53:52"
    assert timefmt.date_only(CRASH) == "01.09.2026"


def test_error_log_line_shows_moscow_time() -> None:
    row = SimpleNamespace(
        id=8,
        occurred_at=CRASH,
        exception_type="TelegramNetworkError",
        exception_message="HTTP Client says - Request timeout error",
        user_tg_id=None,
    )
    assert _error_line(row, {}).startswith("№8 01.09 20:53 ·")


def test_audit_log_line_shows_moscow_time() -> None:
    row = SimpleNamespace(
        created_at=CRASH,
        action_type="user_banned",
        actor_tg_id=None,
        target_tg_id=None,
        target_entity_id=None,
        reason=None,
        meta=None,
    )
    assert _audit_line(row, {}).startswith("01.09 20:53 ·")


def test_the_zone_is_named_where_time_is_shown() -> None:
    """Время без подписи — повод для второй ошибки при разборе первой."""
    assert "МСК" in texts.ERROR_OWNER_DM, "В карточке ошибки пояс должен быть назван."
    assert "московское" in texts.LOGS_HEADER, "В шапке журнала — тоже."
