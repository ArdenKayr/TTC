"""Картинка к мероприятию: обложка поста в Афише.

Пост, собранный вокруг картинки, читают; голый текст пролистывают — поэтому
шаг сделан обязательным. Вся сложность здесь в одном ограничении Telegram:
в подпись под картинкой влезает 1024 символа, а описание мероприятия — до
2000. Значит, пост бывает двух видов, и они правятся разными способами:
подпись у одного, текст у другого. Перепутать — значит получить отказ
Telegram и закрытое мероприятие, которое так и висит в Афише активным.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date

import pytest

from bot import limits, texts
from bot.config import settings
from bot.db.models import ActivityRequest, User
from bot.enums import RequestStatus, UserRole
from bot.routers import activities as activities_router
from bot.services import activity_service, content_service, notification_service
from bot.states.activity_states import ActivityForm

SHORT = "Короткая карточка"
LONG = "я" * (content_service.CAPTION_LIMIT + 1)


class _Bot:
    """Подставной бот: запоминает, что и куда он отправлял."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.calls.append(("message", text, kwargs))
        return _Sent(101)

    async def send_photo(self, chat_id, photo, **kwargs):
        self.calls.append(("photo", photo, kwargs))
        return _Sent(202)

    async def edit_message_text(self, text, **kwargs):
        self.calls.append(("edit_text", text, kwargs))

    async def edit_message_caption(self, **kwargs):
        self.calls.append(("edit_caption", kwargs.get("caption"), kwargs))


class _Sent:
    def __init__(self, message_id: int) -> None:
        self.message_id = message_id


@pytest.fixture
def bot(monkeypatch) -> _Bot:
    # Без номера группы бот в Афишу не пишет вовсе — здесь он нужен любой.
    monkeypatch.setattr(settings, "group_chat_id", -100500, raising=False)
    return _Bot()


def _kinds(bot: _Bot) -> list[str]:
    return [kind for kind, _payload, _kwargs in bot.calls]


# --- Пост в Афише ------------------------------------------------------------


def test_a_short_card_becomes_one_post_with_a_picture(bot) -> None:
    """Ради этого всё и затевалось: картинка и текст — одним постом."""
    post = asyncio.run(notification_service.send_afisha_card(bot, SHORT, "file-1"))

    assert _kinds(bot) == ["photo"]
    assert bot.calls[0][2]["caption"] == SHORT
    assert post.is_caption
    assert post.message_id == 202


def test_a_long_card_does_not_get_lost_because_of_the_caption_limit(bot) -> None:
    """Длинное описание Telegram в подпись не пустит — тогда двумя сообщениями."""
    post = asyncio.run(notification_service.send_afisha_card(bot, LONG, "file-1"))

    assert _kinds(bot) == ["photo", "message"]
    assert bot.calls[0][2].get("caption") is None
    # Помечать при закрытии надо текст, а не подпись пустой картинки.
    assert not post.is_caption
    assert post.message_id == 101


def test_an_activity_without_a_picture_still_gets_posted(bot) -> None:
    """У мероприятий, поданных до этого шага, картинки нет и взяться ей неоткуда."""
    post = asyncio.run(notification_service.send_afisha_card(bot, SHORT))

    assert _kinds(bot) == ["message"]
    assert not post.is_caption


def test_the_mark_goes_where_the_card_actually_is(bot) -> None:
    asyncio.run(notification_service.edit_afisha_card(bot, 202, SHORT, is_caption=True))
    asyncio.run(notification_service.edit_afisha_card(bot, 101, SHORT))

    assert _kinds(bot) == ["edit_caption", "edit_text"]


def test_a_failed_post_is_reported_as_failure(bot, monkeypatch) -> None:
    """Молча потерянная карточка — это мероприятие, которого никто не увидит."""
    from aiogram.exceptions import TelegramAPIError

    async def boom(*args, **kwargs):
        raise TelegramAPIError(method=None, message="no rights")

    monkeypatch.setattr(bot, "send_photo", boom)
    assert asyncio.run(notification_service.send_afisha_card(bot, SHORT, "file-1")) is None


# --- Карточка заявки админам -------------------------------------------------


def test_admins_see_the_picture_with_the_request(bot) -> None:
    asyncio.run(notification_service.send_admin_card(bot, SHORT, "kb", "file-1"))

    assert _kinds(bot) == ["photo"]
    assert bot.calls[0][2]["reply_markup"] == "kb"


def test_decision_buttons_stay_with_the_text_of_the_card(bot) -> None:
    """Иначе админ читает карточку, а кнопки решения ищет под соседней картинкой."""
    asyncio.run(notification_service.send_admin_card(bot, LONG, "kb", "file-1"))

    assert _kinds(bot) == ["photo", "message"]
    assert bot.calls[0][2].get("reply_markup") is None
    assert bot.calls[1][2]["reply_markup"] == "kb"


# --- Шаг анкеты --------------------------------------------------------------


def test_the_picture_step_can_be_returned_to() -> None:
    """Без записи в реестре «⬅️ Шаг назад» с вопроса «что нужно» упал бы."""
    assert ActivityForm.photo.state in activities_router._ASK_BY_NAME


def test_the_step_explains_what_it_wants_instead_of_the_general_answer() -> None:
    """Общий ответ сказал бы «нужен текст» — на этом шаге нужна картинка."""
    assert "картинка" in texts.ACT_PHOTO_NEEDED
    assert "фото" in texts.ACT_PHOTO_AS_FILE
    # Картинку часто шлют файлом: в посте её тогда не видно вовсе.
    assert "файл" in texts.ACT_PHOTO_AS_FILE


def test_the_prompt_says_the_step_cannot_be_skipped() -> None:
    assert "пропустить" in texts.ACT_PHOTO_PROMPT.lower()
    assert texts.BTN.SKIP not in texts.ACT_PHOTO_PROMPT


def test_the_summary_still_fits_the_limits_it_promises() -> None:
    """Сводка с картинкой и без — один и тот же текст, лимиты не разъехались."""
    assert limits.ACT_DESC_MAX > content_service.CAPTION_LIMIT, (
        "если описание стало короче подписи, ветка с двумя сообщениями "
        "больше не нужна — уберите её вместе с afisha_is_caption"
    )


# --- Перенос картинки из заявки в мероприятие --------------------------------


class _ApproveSession:
    """Подставная база: отдаёт заявку и её автора, всё остальное — пустышки."""

    def __init__(self, request, author) -> None:
        self.request = request
        self.author = author
        self.added: list = []

    async def get(self, model, key):
        return self.request if model is ActivityRequest else self.author

    def add(self, obj) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        pass


@pytest.fixture
def approved(monkeypatch):
    """Одобряет заявку с картинкой и записывает, что ушло в Афишу."""
    sent = {}

    async def fake_afisha(bot, text, photo_file_id=None):
        sent["text"] = text
        sent["photo"] = photo_file_id
        return notification_service.AfishaPost(777, is_caption=True)

    async def fake_dm(*args, **kwargs):
        return activity_service.scenario_service.Delivery.SENT

    async def fake_audit(*args, **kwargs):
        pass

    monkeypatch.setattr(activity_service.notification_service, "send_afisha_card", fake_afisha)
    monkeypatch.setattr(activity_service.scenario_service, "dm", fake_dm)
    monkeypatch.setattr(activity_service.audit_repo, "add", fake_audit)

    author = User(
        tg_id=1,
        display_name="Организатор",
        birth_date=date(2000, 1, 1),
        current_role=UserRole.USER,
    )
    request = ActivityRequest(
        request_id=uuid.uuid4(),
        tg_id=1,
        title="Настолки",
        description="Придут все",
        photo_file_id="file-1",
        status=RequestStatus.PENDING,
    )
    session = _ApproveSession(request, author)
    ok, _note = asyncio.run(
        activity_service.approve_activity(session, None, request.request_id, author)
    )
    return {"ok": ok, "sent": sent, "session": session}


def test_the_picture_reaches_the_afisha(approved) -> None:
    """Картинка живёт в заявке, а показать её надо в Афише — перенос обязателен."""
    assert approved["ok"]
    assert approved["sent"]["photo"] == "file-1"


def test_the_activity_remembers_which_kind_of_post_it_got(approved) -> None:
    """Иначе при закрытии бот будет править не то и получит отказ Telegram."""
    activity = approved["session"].added[0]
    assert activity.photo_file_id == "file-1"
    assert activity.afisha_message_id == 777
    assert activity.afisha_is_caption
