"""Сторож связи: считает провалы, а не создаёт впечатление.

Решение «покупать прокси или нет» стоит денег, поэтому опирается на числа:
как часто и надолго пропадает IPv6, единственный рабочий путь к Telegram
с боевого сервера. Здесь проверяется, что сводка считает это честно —
включая самый долгий провал подряд, ради которого всё и затевалось.
"""

from __future__ import annotations

import socket

import pytest

from scripts import net_watch

JOURNAL = """\
2026-09-02T10:00:00Z ipv6=ok:41ms ipv4=fail:5001ms
2026-09-02T10:01:00Z ipv6=fail:5002ms ipv4=fail:5001ms
2026-09-02T10:02:00Z ipv6=fail:5003ms ipv4=fail:5002ms
2026-09-02T10:03:00Z ipv6=fail:5001ms ipv4=fail:5000ms
2026-09-02T10:04:00Z ipv6=ok:39ms ipv4=fail:5000ms
2026-09-02T10:05:00Z ipv6=ok:40ms ipv4=fail:5001ms
"""


@pytest.fixture
def journal(tmp_path):
    path = tmp_path / "netwatch.log"
    path.write_text(JOURNAL, encoding="utf-8")
    return path


def test_report_counts_failures(journal) -> None:
    summary = net_watch.report(journal)
    assert "Проверок: 6" in summary
    assert "ipv6: провалов 3 из 6 (50.0%)" in summary
    assert "ipv4: провалов 6 из 6 (100.0%)" in summary


def test_report_measures_the_longest_outage(journal) -> None:
    """Именно длина провала решает, хватит ли повторов в коде.

    Три проверки подряд с минутным шагом — это две минуты между первой и
    последней неудачей.
    """
    assert "Самый долгий провал IPv6 подряд: 2 мин." in net_watch.report(journal)


def test_broken_lines_are_skipped(tmp_path) -> None:
    """Журнал дописывается на живом сервере — обрывок строки не повод падать."""
    path = tmp_path / "netwatch.log"
    path.write_text(JOURNAL + "мусор\n2026-09-02T10:0", encoding="utf-8")
    assert "Проверок: 6" in net_watch.report(path)


def test_empty_journal_says_so(tmp_path) -> None:
    path = tmp_path / "netwatch.log"
    path.write_text("", encoding="utf-8")
    assert "пока нет ни одной проверки" in net_watch.report(path)


def test_line_format_is_machine_readable(monkeypatch) -> None:
    """Строку пишет cron, читает сводка — формат должен пережить оба."""
    monkeypatch.setattr(
        net_watch, "probe", lambda family: (family == socket.AF_INET6, 42.0)
    )
    line = net_watch.once()
    assert "ipv6=ok:42ms" in line
    assert "ipv4=fail:42ms" in line
    parsed = net_watch._parse(line)
    assert parsed is not None
    assert parsed[1] == {"ipv6": True, "ipv4": False}
