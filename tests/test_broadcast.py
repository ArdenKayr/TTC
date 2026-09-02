"""Рассылка владельца: письмо всем, без приписок и без следа в разделах.

Появилась из живой беды: группу сообщества заблокировал Telegram, её пришлось
пересоздавать, и всем участникам понадобилось сказать об этом — каждому в
личку. Раздел «Обновления» для такого не годится: там новости о самом боте,
и запись оттуда никто не увидит, пока не откроет раздел.

Отличия от рассылки обновления, ради которых всё и делалось: текст уходит
ровно таким, каким его написали, и никуда не подшивается. Общая у них только
доставка — она живёт в одном месте на обе задачи.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramForbiddenError

from bot.enums import AuditAction, UserRole
from bot.services import broadcast_service


class _Bot:
    """Телеграм, который принимает всё, кроме личек тех, кто закрыл бота."""

    def __init__(self, blocked: set[int] | None = None) -> None:
        self.blocked = blocked or set()
        self.messages: list[tuple[int, str]] = []
        self.files: list[tuple[int, str, str | None]] = []

    async def send_message(self, tg_id: int, text: str, **kwargs) -> None:
        if tg_id in self.blocked:
            raise TelegramForbiddenError(method=None, message="bot was blocked by the user")
        self.messages.append((tg_id, text))

    async def send_photo(self, tg_id: int, file_id: str, caption: str | None = None, **kw) -> None:
        if tg_id in self.blocked:
            raise TelegramForbiddenError(method=None, message="bot was blocked by the user")
        self.files.append((tg_id, file_id, caption))

    async def send_document(self, tg_id: int, file_id: str, caption: str | None = None, **kw):
        await self.send_photo(tg_id, file_id, caption)


class _Session:
    """База: список получателей и запись в журнал действий."""

    def __init__(self, tg_ids: list[int]) -> None:
        self.tg_ids = tg_ids
        self.commits = 0

    async def scalars(self, *args, **kwargs):
        return list(self.tg_ids)

    async def commit(self) -> None:
        self.commits += 1


@pytest.fixture(autouse=True)
def _no_pauses(monkeypatch):
    """Паузы между письмами настоящие — в тестах они не нужны."""
    monkeypatch.setattr(broadcast_service, "SEND_PAUSE", 0)


@pytest.fixture
def audit(monkeypatch) -> list[tuple]:
    written: list[tuple] = []

    async def fake_add(session, action, **kwargs):
        written.append((action, kwargs))

    monkeypatch.setattr(broadcast_service.audit_repo, "add", fake_add)
    return written


def _broadcast(bot, session, text="Группа переехала.", file_id=None, file_type=None):
    owner = SimpleNamespace(tg_id=1, current_role=UserRole.OWNER)
    return asyncio.run(
        broadcast_service.broadcast(session, bot, owner, text, file_id, file_type)
    )


def test_everyone_gets_the_letter(audit) -> None:
    bot, session = _Bot(), _Session([10, 20, 30])
    delivered, total = _broadcast(bot, session)
    assert (delivered, total) == (3, 3)
    assert [tg_id for tg_id, _ in bot.messages] == [10, 20, 30]


def test_text_goes_out_exactly_as_written(audit) -> None:
    """Никаких приписок: письмо владельца — это его слова, а не пост бота."""
    bot, session = _Bot(), _Session([10])
    _broadcast(bot, session, text="Группа переехала, зайдите за новой ссылкой.")
    assert bot.messages == [(10, "Группа переехала, зайдите за новой ссылкой.")]


def test_closed_chats_are_skipped_and_counted(audit) -> None:
    """Telegram не даёт боту писать первым — это не сбой, а отказ адресата.

    Владельцу важно увидеть разницу между «отправлено всем» и «дошло не всем»,
    поэтому считаются обе величины.
    """
    bot, session = _Bot(blocked={20}), _Session([10, 20, 30])
    delivered, total = _broadcast(bot, session)
    assert (delivered, total) == (2, 3)
    assert [tg_id for tg_id, _ in bot.messages] == [10, 30]


def test_banned_are_not_recipients() -> None:
    """Забаненный остаётся в базе, но бот с ним не разговаривает.

    Смотрим сам запрос: получатели набираются один раз, и ошибка здесь
    означала бы письмо тому, кого из сообщества выгнали.
    """
    captured = {}

    class _CheckingSession(_Session):
        async def scalars(self, query, *args, **kwargs):
            captured["sql"] = str(query.compile(compile_kwargs={"literal_binds": True}))
            return list(self.tg_ids)

    asyncio.run(broadcast_service.recipients(_CheckingSession([10])))
    sql = captured["sql"].lower()
    assert "current_role" in sql, "Отбор идёт по роли."
    assert f"!= '{UserRole.BANNED.value}'" in sql, "Отсекаться должны именно забаненные."


def test_letter_with_a_photo_travels_as_a_caption(audit) -> None:
    bot, session = _Bot(), _Session([10])
    _broadcast(bot, session, text="Короткая подпись", file_id="ph1", file_type="photo")
    assert bot.files == [(10, "ph1", "Короткая подпись")]
    assert not bot.messages


def test_long_text_is_sent_apart_from_the_file(audit) -> None:
    """В подпись влезает не всё — иначе Telegram обрежет письмо молча."""
    long_text = "т" * 2000
    bot, session = _Bot(), _Session([10])
    _broadcast(bot, session, text=long_text, file_id="ph1", file_type="photo")
    assert bot.files == [(10, "ph1", None)]
    assert bot.messages == [(10, long_text)]


def test_broadcast_is_written_to_the_log(audit) -> None:
    """След должен остаться: рассылку не отозвать, и она видна всем участникам."""
    bot, session = _Bot(), _Session([10, 20])
    _broadcast(bot, session)
    assert len(audit) == 1
    action, kwargs = audit[0]
    assert action is AuditAction.BROADCAST_SENT
    assert kwargs["actor_tg_id"] == 1


def test_letter_leaves_no_trace_in_sections(audit, monkeypatch) -> None:
    """Рассылка не трогает раздел «Обновления» — там новости о самом боте.

    Проверяется тем, что до хранилища разделов дело вообще не доходит: иначе
    письмо про переезд группы затёрло бы архив обновлений.
    """
    from bot.services import update_service

    def boom(*args, **kwargs):
        raise AssertionError("рассылка не должна трогать разделы")

    monkeypatch.setattr(update_service.content_repo, "get_or_create", boom)
    bot, session = _Bot(), _Session([10])
    _broadcast(bot, session)
    assert bot.messages
