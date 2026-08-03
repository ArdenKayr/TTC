"""Выкатывает проект на боевой сервер.

Делает то же, что делалось руками (`git archive` → `scp` → пересборка
контейнера), плюс проверки, которые руками пропускаются первыми:

* в проекте нет несохранённых изменений — на сервер уезжает только то, что
  зафиксировано в git, иначе выкатывается не то, что видишь у себя;
* тесты прогоняются целиком;
* выкатка подтверждается словом, чтобы случайный двойной клик не уехал живым
  пользователям.

Запуск: двойной клик по «бой-выкатить.bat» в корне проекта.
Из командной строки: python -m scripts.deploy
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SERVER = "root@45.91.238.177"
KEY = Path.home() / ".ssh" / "ttc_vps"
REMOTE_PATH = "/opt/ttc"


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
    print("Прогоняю тесты…")
    python = ROOT / ".venv" / "Scripts" / "python.exe"
    run([str(python) if python.exists() else sys.executable, "-m", "pytest", "-q"])


def confirm(sha: str, subject: str) -> None:
    print()
    print(f"Сейчас на боевой сервер уедет: {sha[:8]} — {subject}")
    print("Его сразу увидят живые участники сообщества.")
    answer = input("Напишите ДА (заглавными), чтобы продолжить: ").strip()
    if answer != "ДА":
        raise DeployError("Отменено — ничего не изменилось.")


def upload(sha: str) -> None:
    archive = ROOT / ".git" / "ttc-deploy.tar.gz"
    print(f"Собираю архив коммита {sha[:8]}…")
    run(["git", "archive", "--format=tar.gz", "-o", str(archive), "HEAD"])

    print(f"Копирую на сервер, в {REMOTE_PATH}…")
    run(["scp", "-i", str(KEY), str(archive), f"{SERVER}:{REMOTE_PATH}/ttc-deploy.tar.gz"])
    archive.unlink(missing_ok=True)

    print("Распаковываю и пересобираю бота (структура базы подтянется сама)…")
    ssh(
        f"cd {REMOTE_PATH} && tar xzf ttc-deploy.tar.gz && rm ttc-deploy.tar.gz "
        f"&& docker compose up -d --build bot"
    )


def show_log() -> None:
    print("\nПоследние строки журнала бота:")
    ssh(f"cd {REMOTE_PATH} && docker compose logs --tail 15 bot")


def deploy(*, skip_tests: bool, assume_yes: bool) -> None:
    check_clean_tree()
    sha, subject = head_commit()

    if skip_tests:
        print("!! Тесты пропущены (--no-tests). Вы выкатываете непроверенный код.")
    else:
        check_tests()

    if not assume_yes:
        confirm(sha, subject)

    upload(sha)
    show_log()

    print(f"\nГотово: на сервере стоит {sha[:8]} — {subject}")
    print("Первые полчаса стоит присматривать за журналом ошибок: «🛠 Админство» → «📜 Логи».")


def main() -> int:
    parser = argparse.ArgumentParser(description="Выкатить проект на боевой сервер")
    parser.add_argument("--no-tests", action="store_true", help="не прогонять pytest")
    parser.add_argument("--yes", action="store_true", help="не спрашивать подтверждения")
    args = parser.parse_args()

    if not KEY.exists():
        print(f"Не найден ключ для входа на сервер: {KEY}")
        return 1

    try:
        deploy(skip_tests=args.no_tests, assume_yes=args.yes)
    except DeployError as error:
        print(f"\nНе выкатили.\n\n{error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
