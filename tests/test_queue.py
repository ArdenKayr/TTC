"""Очередь разбора: заявку можно разобрать не сейчас, а когда дойдут руки.

Просьба владельца 09.09.2026: «хочу принимать мероприятие не сразу, а,
допустим, на следующий день; но кнопки в Телеграме через какое-то время не
работают». Кнопки на старой карточке действительно подводят (об этом
`test_review_card`), поэтому опираться на неё нельзя вовсе: очередь смотрит
в базу и выдаёт свежую карточку со свежими кнопками в любой момент.

Тот же раздел закрывает и вторую беду, найденную при расчёте нагрузки на
тысячу человек: карточка может не дойти до админ-чата (упёрлись в лимит
Telegram — 20 сообщений в минуту в одну группу), а заявка при этом лежит в
базе и ждёт. Раньше увидеть её было негде.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy.dialects import postgresql

from bot import texts
from bot.enums import PermissionModule, RequestStatus
from bot.services import queue_service

ADMIN_ID = 1419203590


def _sql(kind_key: str) -> str:
    return str(
        queue_service.statement(kind_key).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


# --- Что именно очередь считает ждущим решения ---


@pytest.mark.parametrize("kind", [k.key for k in queue_service.KINDS])
def test_only_pending_requests_are_queued(kind: str) -> None:
    """В очереди — только то, по чему решения ещё нет."""
    assert f"'{RequestStatus.PENDING.value}'" in _sql(kind)


@pytest.mark.parametrize("kind", [k.key for k in queue_service.KINDS])
def test_oldest_first(kind: str) -> None:
    """Разбирают с самых давних: дольше всех ждёт тот, кто подал раньше."""
    assert "ORDER BY" in _sql(kind) and "created_at" in _sql(kind)


def test_registration_waiting_for_a_university_is_not_queued() -> None:
    """Заявка, ждущая решения по новому вузу, админу пока не показывается.

    Такая заявка ждёт не админа: её карточка отправляется сама, после решения
    по вузу. Показать её в очереди — значит позвать одобрить человека с вузом,
    которого в справочнике ещё нет.
    """
    sql = _sql("reg")
    assert "LEFT OUTER JOIN university_requests" in sql, (
        "Без связи с заявкой на вуз отличить готовые заявки от ждущих нельзя."
    )
    assert "university_request_id IS NULL" in sql
    assert sql.count(f"'{RequestStatus.PENDING.value}'") == 2, (
        "Условий два: сама заявка ждёт решения, а вот заявка на вуз — уже нет."
    )


def test_unknown_kind_is_a_mistake_not_an_empty_list() -> None:
    """Испорченный ключ вида — ошибка кода, а не «ничего не нашлось»."""
    with pytest.raises(ValueError):
        queue_service.statement("нет такого")


# --- Кто какие виды заявок видит ---


def test_registration_admin_sees_only_registrations() -> None:
    """Модули прав решают состав очереди: чужого в ней не видно."""
    kinds = queue_service.allowed({PermissionModule.REGISTRATION.value})
    assert [k.key for k in kinds] == ["reg"]


def test_activities_admin_sees_events_and_votes() -> None:
    """Один модуль «Мероприятия» открывает два вида заявок сразу."""
    kinds = queue_service.allowed({PermissionModule.ACTIVITIES.value})
    assert [k.key for k in kinds] == ["act", "vote"]


def test_every_kind_belongs_to_a_real_module() -> None:
    """Вид заявок без модуля прав открылся бы кому попало."""
    for kind in queue_service.KINDS:
        assert isinstance(kind.module, PermissionModule)


# --- Сводка ---


def test_summary_hides_empty_kinds() -> None:
    """В сводке только то, что ждёт: нули — лишний шум."""
    summary = queue_service.render_summary({"reg": 3, "act": 0, "vote": 2})
    assert texts.BTN.QUEUE_REG in summary
    assert texts.BTN.QUEUE_VOTE in summary
    assert texts.BTN.QUEUE_ACT not in summary
    assert "3" in summary and "2" in summary


# --- Отправка карточек ---


class _Bot:
    """Телеграм, который может отказать в отдельной карточке."""

    def __init__(self, fail_on: set[int] | None = None) -> None:
        self.fail_on = fail_on or set()
        self.attempts = 0
        self.sent: list[str] = []
        self.photos: list[tuple[str, str | None]] = []

    def _try(self) -> None:
        """Считает попытки, а не удачи: отказ тоже расходует свой номер."""
        attempt = self.attempts
        self.attempts += 1
        if attempt in self.fail_on:
            raise TelegramBadRequest(method=None, message="Too Many Requests")

    async def send_message(self, chat_id, text, reply_markup=None, message_thread_id=None):
        self._try()
        self.sent.append(text)

    async def send_photo(
        self, chat_id, photo, caption=None, reply_markup=None, message_thread_id=None
    ):
        self._try()
        self.photos.append((photo, caption))


def _cards(count: int, photo: str | None = None) -> list[queue_service.Card]:
    return [
        queue_service.Card(text=f"Заявка {i}", keyboard=None, photo_file_id=photo)
        for i in range(count)
    ]


def test_all_cards_are_sent() -> None:
    bot = _Bot()
    shown = asyncio.run(queue_service.send(bot, ADMIN_ID, _cards(3)))
    assert shown == 3
    assert bot.sent == ["Заявка 0", "Заявка 1", "Заявка 2"]


def test_one_refused_card_does_not_stop_the_rest() -> None:
    """Отказ по одной карточке — не повод не показать остальные.

    Заявка при этом не теряется: она остаётся в очереди и придёт со следующим
    нажатием. А вот бросить весь список из-за одной — значит скрыть от админа
    работу, которая его ждёт.
    """
    bot = _Bot(fail_on={1})
    shown = asyncio.run(queue_service.send(bot, ADMIN_ID, _cards(3)))
    assert shown == 2, "Дошли две из трёх — столько и надо назвать честно."
    assert bot.sent == ["Заявка 0", "Заявка 2"]


def test_event_card_keeps_its_cover() -> None:
    """Заявка на мероприятие показывается с обложкой — как и в админ-чате."""
    bot = _Bot()
    asyncio.run(queue_service.send(bot, ADMIN_ID, _cards(1, photo="обложка")))
    assert bot.photos == [("обложка", "Заявка 0")]
    assert bot.sent == []


# --- Карточка мероприятия, у которого удалили автора ---


def test_deleted_author_does_not_break_the_queue() -> None:
    """Автора удалили из базы — очередь всё равно должна открыться.

    Записи людей удаляются со ссылкой SET NULL: заявка остаётся жить без
    автора. Раньше такая заявка уронила бы отрисовку, а с ней и весь список.
    """
    from bot.services import activity_service

    request = SimpleNamespace(
        title="Ограбление казино",
        description="Как в кино",
        organizers_text=None,
        plan_url=None,
        chat_url=None,
        admin_comment=None,
        needs_text=None,
    )
    card = activity_service.build_act_card(None, request)
    assert texts.USER_DELETED_LABEL in card
