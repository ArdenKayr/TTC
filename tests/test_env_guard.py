"""Тестовый бот не должен попасть в боевые чаты.

Контура два, файлы проекта у них одинаковые, различается только `.env`.
Значит перепутать настройки — вопрос одной невнимательной копии, а цена
ошибки высокая: тестовый бот такой же админ с правом удалять сообщения, и в
боевой группе он начнёт удалять там сообщения и банить людей по-настоящему.

Поэтому проверка стоит в `bot/config.py` и срабатывает при старте: контейнер
просто не поднимется. Здесь — сторож этой проверки.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from bot.config import PRODUCTION_CHATS, Settings

BASE = {
    "bot_token": "123456:test",
    "database_url": "postgresql+asyncpg://ttc:pass@postgres:5432/ttc",
    "redis_url": "redis://redis:6379/0",
}


def settings(**overrides) -> Settings:
    # _env_file=None: у разработчика в корне лежит свой .env, и тест не должен
    # зависеть от того, что в нём написано сегодня.
    return Settings(_env_file=None, **BASE, **overrides)


def test_test_bot_refuses_production_admin_chat():
    with pytest.raises(ValidationError) as error:
        settings(env_name="test", admin_chat_id=-1004492113804, group_chat_id=-100777)
    assert "боевые чаты" in str(error.value)


def test_test_bot_refuses_production_group():
    with pytest.raises(ValidationError) as error:
        settings(env_name="test", admin_chat_id=-100777, group_chat_id="@The_True_Course_SPB")
    assert "боевые чаты" in str(error.value)


def test_production_chat_check_ignores_letter_case():
    """Имя группы можно написать как угодно — проверка всё равно сработает."""
    with pytest.raises(ValidationError):
        settings(env_name="test", admin_chat_id=-100777, group_chat_id="@the_TRUE_course_spb")


def test_test_bot_with_its_own_chats_starts():
    cfg = settings(env_name="test", admin_chat_id=-100555, group_chat_id=-100777)
    assert cfg.is_test


def test_production_bot_keeps_production_chats():
    """Проверка касается только тестового контура — боевой работает как работал."""
    cfg = settings(admin_chat_id=-1004492113804, group_chat_id="@The_True_Course_SPB")
    assert not cfg.is_test


def test_env_name_defaults_to_production():
    """Забыли переменную — считаем бот боевым: так безопаснее."""
    assert not settings(admin_chat_id=-100555).is_test


def test_production_chats_are_written_the_same_way_as_in_env_example():
    """Список сверяется с .env.example: боевые значения не должны разъехаться."""
    example = (
        __import__("pathlib").Path(__file__).resolve().parent.parent / ".env.example"
    ).read_text(encoding="utf-8")
    for chat in PRODUCTION_CHATS:
        assert chat.lower() in example.lower(), (
            f"{chat} есть в списке боевых чатов, но не в .env.example — "
            "либо чат сменился, либо список устарел"
        )
