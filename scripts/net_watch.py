"""Сторож связи с Telegram: измеряет, а не гадает.

С боевого сервера api.telegram.org доступен по IPv6 и недоступен по IPv4.
Пока IPv6 жив, бот отвечает за доли секунды; когда IPv6 на секунды
пропадает, запрос уходит в мёртвый IPv4 и виснет. Вопрос, ради которого
написан этот скрипт, один: **как часто и надолго пропадает IPv6**. От
ответа зависит, хватит ли настроек в коде или нужен свой прокси за деньги.

Как пользоваться (на сервере):

    # одна проверка — печатает строку, cron дописывает её в журнал
    docker exec ttc-bot-1 python /app/scripts/net_watch.py once

    # сводка за всё накопленное
    python3 /opt/ttc/scripts/net_watch.py report /opt/ttc/data/netwatch.log

Проверка идёт изнутри контейнера бота — важно мерить ровно ту сеть, по
которой ходит сам бот, а не сеть хоста: у них разные маршруты.

Скрипт намеренно обходится одной стандартной библиотекой: он должен
работать и там, где зависимостей проекта нет.
"""

from __future__ import annotations

import socket
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOST = "api.telegram.org"
PORT = 443
TIMEOUT = 5.0  # столько же, сколько бот отводит на соединение

FAMILIES = (("ipv6", socket.AF_INET6), ("ipv4", socket.AF_INET))


def probe(family: int) -> tuple[bool, float]:
    """Удалось ли соединиться и сколько это заняло миллисекунд."""
    started = time.monotonic()
    try:
        infos = socket.getaddrinfo(HOST, PORT, family, socket.SOCK_STREAM)
    except OSError:
        return False, (time.monotonic() - started) * 1000
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.settimeout(TIMEOUT)
    try:
        sock.connect(infos[0][4])
        return True, (time.monotonic() - started) * 1000
    except OSError:
        return False, (time.monotonic() - started) * 1000
    finally:
        sock.close()


def once() -> str:
    """Строка журнала: время и итог по каждому протоколу."""
    moment = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    parts = [moment]
    for name, family in FAMILIES:
        ok, ms = probe(family)
        parts.append(f"{name}={'ok' if ok else 'fail'}:{ms:.0f}ms")
    return " ".join(parts)


def _parse(line: str) -> tuple[datetime, dict[str, bool]] | None:
    """Разбирает строку журнала. Мусор молча пропускаем — журнал дописывается."""
    parts = line.split()
    if len(parts) < len(FAMILIES) + 1:
        return None
    try:
        moment = datetime.strptime(parts[0], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    result = {}
    for chunk in parts[1:]:
        name, _, rest = chunk.partition("=")
        result[name] = rest.startswith("ok")
    return moment, result


def report(path: Path) -> str:
    """Сводка: как часто пропадала связь и какой был самый долгий провал."""
    rows = [parsed for line in path.read_text(encoding="utf-8").splitlines() if (parsed := _parse(line))]
    if not rows:
        return f"В {path} пока нет ни одной проверки."

    lines = [
        f"Проверок: {len(rows)}",
        f"Период: с {rows[0][0]:%d.%m %H:%M} по {rows[-1][0]:%d.%m %H:%M} UTC",
        "",
    ]
    for name, _family in FAMILIES:
        failures = [moment for moment, result in rows if not result.get(name, False)]
        share = len(failures) * 100 / len(rows)
        lines.append(f"{name}: провалов {len(failures)} из {len(rows)} ({share:.1f}%)")

    # Самый длинный непрерывный провал IPv6 — именно он превращается в
    # молчание бота: пока IPv6 лежит, идти боту больше некуда.
    longest = timedelta()
    started: datetime | None = None
    previous: datetime | None = None
    for moment, result in rows:
        if not result.get("ipv6", False):
            started = started or moment
            previous = moment
        elif started is not None and previous is not None:
            longest = max(longest, previous - started)
            started = previous = None
    if started is not None and previous is not None:
        longest = max(longest, previous - started)

    lines.append("")
    lines.append(f"Самый долгий провал IPv6 подряд: {int(longest.total_seconds() // 60)} мин.")
    lines.append(
        "Если провалы редки и коротки — хватит настроек в коде. "
        "Если IPv6 лежит минутами и часто — нужен свой прокси."
    )
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else "once"
    if command == "once":
        print(once())
        return 0
    if command == "report":
        if len(argv) < 3:
            print("Укажите файл журнала: net_watch.py report <файл>")
            return 2
        print(report(Path(argv[2])))
        return 0
    print(f"Непонятная команда {command!r}. Есть once и report.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
