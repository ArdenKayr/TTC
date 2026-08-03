"""Выкатывает проект на сервер: сначала в тестовый контур, потом на бой.

Контуров два, оба на одной машине (docs/TEST_ENV.md):

    /opt/ttc-test — тестовый бот, своя база, тестовые чаты;
    /opt/ttc      — боевой.

Главное, что делает этот скрипт помимо копирования файлов, — не даёт выкатить
на бой то, чего не видел тестовый контур. Правило 6 регламента обновлений
(docs/RELEASE_RULES.md) требует именно такого порядка, а держать его на памяти
человека бессмысленно: в спешке порядок нарушается первым. Поэтому при выкатке
в тест на сервере остаётся отметка с номером коммита, а выкатка на бой её
читает и сверяет.

Запуск: двойной клик по «тест-выкатить.bat» или «бой-выкатить.bat» в корне.
Из командной строки: python -m scripts.deploy test
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SERVER = "root@45.91.238.177"
KEY = Path.home() / ".ssh" / "ttc_vps"

# Файл-отметка на сервере: какой коммит там сейчас стоит и когда его выкатили.
# Лежит вне git, поэтому распаковка архива поверх его не затирает.
STAMP = ".deployed"


@dataclass(frozen=True)
class Target:
    key: str
    path: str
    name: str


TARGETS = {
    "test": Target("test", "/opt/ttc-test", "тестовый контур"),
    "prod": Target("prod", "/opt/ttc", "БОЕВОЙ сервер"),
}


class DeployError(Exception):
    """Понятная остановка: показываем причину, а не трассировку."""


def run(args: list[str], capture: bool = False) -> str:
    result = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=capture,
        check=False,  # разбираем код возврата сами, чтобы объяснить его по-человечески
    )
    if result.returncode != 0:
        if capture:
            print(result.stdout or "", end="")
            print(result.stderr or "", end="")
        raise DeployError(f"Команда завершилась с ошибкой:\n  {' '.join(args)}")
    return (result.stdout or "").strip() if capture else ""


def ssh(command: str, capture: bool = False) -> str:
    return run(["ssh", "-i", str(KEY), SERVER, command], capture=capture)


def head_commit() -> tuple[str, str]:
    sha = run(["git", "rev-parse", "HEAD"], capture=True)
    subject = run(["git", "log", "-1", "--pretty=%s"], capture=True)
    return sha, subject


def check_clean_tree() -> None:
    dirty = run(["git", "status", "--porcelain"], capture=True)
    if dirty:
        raise DeployError(
            "В проекте есть несохранённые изменения:\n"
            + "\n".join(f"  {line}" for line in dirty.splitlines())
            + "\n\nНа сервер уезжает только то, что зафиксировано в git. "
            "Сделайте коммит — иначе выкатите не то, что видите у себя."
        )


def check_tests() -> None:
    print("Прогоняю тесты (это правило 5 регламента: документация и карта сверяются)…")
    python = ROOT / ".venv" / "Scripts" / "python.exe"
    run([str(python) if python.exists() else sys.executable, "-m", "pytest", "-q"])


def read_stamp(target: Target) -> tuple[str, str] | None:
    """Что и когда выкатывали в этот контур. None — отметки ещё нет."""
    raw = ssh(f"cat {target.path}/{STAMP} 2>/dev/null || true", capture=True)
    if not raw:
        return None
    parts = raw.split(None, 1)
    return parts[0], (parts[1] if len(parts) > 1 else "")


def check_tested(sha: str) -> None:
    """Правило 6: на бой едет только то, что потыкали в тесте."""
    stamp = read_stamp(TARGETS["test"])
    if stamp is None:
        raise DeployError(
            "Тестовый контур ещё ни разу не обновлялся, поэтому проверить, что "
            "обновление кто-то щупал, невозможно.\n"
            "Сначала «тест-выкатить.bat», потом тестировщики, потом бой.\n"
            "Если контура ещё нет — как его завести, написано в docs/TEST_ENV.md."
        )
    tested_sha, when = stamp
    if tested_sha != sha:
        raise DeployError(
            "На бой едет то, чего не было в тесте.\n"
            f"  в тестовом контуре: {tested_sha[:8]} (выкачено {when})\n"
            f"  вы выкатываете:     {sha[:8]}\n\n"
            "Правило 6 регламента обновлений: сначала тестовый контур, "
            "тестировщики тыкают, и только потом боевой сервер.\n"
            "Выкатите то же самое в тест («тест-выкатить.bat») и дайте проверить."
        )


def confirm(target: Target, sha: str, subject: str) -> None:
    print()
    print(f"Сейчас на {target.name} уедет: {sha[:8]} — {subject}")
    answer = input("Напишите ДА (заглавными), чтобы продолжить: ").strip()
    if answer != "ДА":
        raise DeployError("Отменено — ничего не изменилось.")


def upload(target: Target, sha: str) -> None:
    archive = ROOT / ".git" / "ttc-deploy.tar.gz"
    print(f"Собираю архив коммита {sha[:8]}…")
    run(["git", "archive", "--format=tar.gz", "-o", str(archive), "HEAD"])

    print(f"Копирую на сервер, в {target.path}…")
    run(["scp", "-i", str(KEY), str(archive), f"{SERVER}:{target.path}/ttc-deploy.tar.gz"])
    archive.unlink(missing_ok=True)

    stamped = f"{sha} {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    print("Распаковываю и пересобираю бота (база подтянется сама)…")
    ssh(
        f"cd {target.path} && tar xzf ttc-deploy.tar.gz && rm ttc-deploy.tar.gz "
        f"&& printf '%s\\n' '{stamped}' > {STAMP} "
        f"&& docker compose up -d --build bot"
    )


def show_log(target: Target) -> None:
    print("\nПоследние строки журнала бота:")
    ssh(f"cd {target.path} && docker compose logs --tail 15 bot")


def deploy(target: Target, *, skip_tests: bool, assume_yes: bool, force: bool) -> None:
    check_clean_tree()
    sha, subject = head_commit()

    if skip_tests:
        print("!! Тесты пропущены (--no-tests). Вы выкатываете непроверенный код.")
    else:
        check_tests()

    if target.key == "prod":
        if force:
            print("!! Проверка «сначала тест» отключена (--force). Правило 6 нарушено осознанно.")
        else:
            check_tested(sha)
        if not assume_yes:
            confirm(target, sha, subject)

    upload(target, sha)
    show_log(target)

    print(f"\nГотово: на {target.name} стоит {sha[:8]} — {subject}")
    if target.key == "test":
        print("Теперь пусть тестировщики пройдут проверки обновления.")
        print("Когда всё хорошо — «бой-выкатить.bat».")


def main() -> int:
    parser = argparse.ArgumentParser(description="Выкатить проект на сервер")
    parser.add_argument("target", choices=sorted(TARGETS), help="куда выкатываем")
    parser.add_argument("--no-tests", action="store_true", help="не прогонять pytest")
    parser.add_argument("--yes", action="store_true", help="не спрашивать подтверждения")
    parser.add_argument(
        "--force", action="store_true", help="бой без проверки «сначала тест» (правило 6)"
    )
    args = parser.parse_args()

    if not KEY.exists():
        print(f"Не найден ключ для входа на сервер: {KEY}")
        return 1

    try:
        deploy(
            TARGETS[args.target],
            skip_tests=args.no_tests,
            assume_yes=args.yes,
            force=args.force,
        )
    except DeployError as error:
        print(f"\nНе выкатили.\n\n{error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
