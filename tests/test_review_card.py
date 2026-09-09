"""Итог разбора обязан дойти до админа, даже если карточку править нельзя.

Жалоба владельца 09.09.2026: «при приёме мероприятий кнопки не работают».
Выяснилось, что ломаются они не от времени — ломается попытка дописать итог
в карточку, и происходит это после того, как решение уже применено. Со
стороны это выглядит одинаково: часики с кнопки пропали, в карточке ничего
не изменилось, кнопки на месте — значит, «не сработало». На деле
мероприятие в этот момент уже одобрено.

Причин у неудачной правки три, и все три проверяются здесь:

1. У карточки мероприятия есть обложка — это фото с подписью, а не текст.
   Правку текста Telegram в таком сообщении запрещает.
2. Подпись вмещает 1024 символа, и дописанный итог в неё может не влезть.
3. Старую карточку Telegram присылает без содержимого — заглушкой
   `InaccessibleMessage`, в которой есть только номера чата и сообщения.

Во всех трёх случаях итог должен дойти отдельным сообщением рядом с
карточкой, а не пропасть вместе с ошибкой в журнале.
"""

from __future__ import annotations

import asyncio

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Chat, InaccessibleMessage

from bot import texts
from bot.routers.admin import review_ui

ADMIN_CHAT = -1004366985565
CARD_ID = 777
NOTE = "✅ Принята — Черешня"


class _Bot:
    """Бот, который запоминает отправленное мимо карточки."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_message(self, chat_id, text, reply_parameters=None) -> None:
        self.sent.append(
            {"chat_id": chat_id, "text": text, "reply_parameters": reply_parameters}
        )


class _Card:
    """Живая карточка в админ-чате: текстовая или с обложкой."""

    def __init__(self, *, caption: str | None = None, edit_error: Exception | None = None):
        self.text = None if caption is not None else "Заявка на мероприятие"
        self.caption = caption
        self.html_text = caption if caption is not None else self.text
        self.edit_error = edit_error
        self.chat = Chat(id=ADMIN_CHAT, type="supergroup")
        self.message_id = CARD_ID
        self.edited_text: str | None = None
        self.edited_caption: str | None = None
        self.replies: list[str] = []

    async def edit_text(self, text: str, reply_markup=None) -> None:
        if self.edit_error is not None:
            raise self.edit_error
        self.edited_text = text

    async def edit_caption(self, caption: str, reply_markup=None) -> None:
        if self.edit_error is not None:
            raise self.edit_error
        self.edited_caption = caption

    async def reply(self, text: str) -> None:
        # Карточки нет в чате — не выйдет ни поправить её, ни ответить на неё.
        if self.edit_error is not None:
            raise self.edit_error
        self.replies.append(text)


class _Callback:
    def __init__(self, message) -> None:
        self.message = message
        self.bot = _Bot()
        self.from_user = type("U", (), {"id": 1419203590})()


def _show(message, ok: bool = True, note: str = NOTE) -> _Callback:
    callback = _Callback(message)
    asyncio.run(review_ui.show_result(callback, ok, note))
    return callback


def test_text_card_is_edited_as_before() -> None:
    """Обычная текстовая карточка правится текстом — как и раньше."""
    callback = _show(_Card())
    assert callback.message.edited_text == "Заявка на мероприятие\n\n" + NOTE
    assert callback.bot.sent == [], "Лишних сообщений в чате быть не должно."


def test_photo_card_is_edited_as_caption() -> None:
    """У карточки с обложкой правится подпись: текста в ней нет вовсе.

    Обложка у заявки на мероприятие обязательна, поэтому все такие карточки —
    фотографии с подписью. Правка текста в них запрещена Telegram, и до этой
    починки итог по мероприятиям не появлялся в карточке никогда.
    """
    callback = _show(_Card(caption="Заявка на мероприятие"))
    assert callback.message.edited_caption == "Заявка на мероприятие\n\n" + NOTE
    assert callback.message.edited_text is None, (
        "Правка текста у фотографии запрещена — Telegram ответит отказом."
    )


def test_result_survives_a_card_that_cannot_be_edited() -> None:
    """Правка не прошла (итог не влез в подпись) — итог идёт рядом с карточкой."""
    refusal = TelegramBadRequest(method=None, message="MESSAGE_CAPTION_TOO_LONG")
    callback = _show(_Card(caption="Заявка", edit_error=refusal))
    assert len(callback.bot.sent) == 1, "Итог решения не имеет права потеряться."
    sent = callback.bot.sent[0]
    assert sent["text"] == NOTE
    assert sent["chat_id"] == ADMIN_CHAT
    assert sent["reply_parameters"].message_id == CARD_ID, (
        "Ответом на карточку — иначе в чате с темами сообщение уйдёт не в ту тему."
    )


def _old_card() -> InaccessibleMessage:
    """Карточка, которую Telegram уже не присылает целиком."""
    return InaccessibleMessage(chat=Chat(id=ADMIN_CHAT, type="supergroup"), message_id=CARD_ID)


def test_old_card_still_delivers_the_result() -> None:
    """Заявку разобрали назавтра: у старой карточки нет текста, итог всё равно доходит."""
    callback = _show(_old_card())
    assert len(callback.bot.sent) == 1, (
        "Именно здесь бот и падал: у заглушки нет ни текста, ни метода «ответить»."
    )
    sent = callback.bot.sent[0]
    assert sent["text"] == NOTE
    assert sent["reply_parameters"].message_id == CARD_ID
    assert sent["reply_parameters"].allow_sending_without_reply is True, (
        "Карточку могли удалить — тогда сообщение должно уйти всё равно."
    )


def test_old_card_explains_a_refusal_too() -> None:
    """По старой карточке нажали второй раз — объяснение тоже должно дойти."""
    callback = _show(_old_card(), ok=False, note=texts.REVIEW_ALREADY_PROCESSED)
    assert [s["text"] for s in callback.bot.sent] == [texts.REVIEW_ALREADY_PROCESSED]


def test_click_without_a_message_falls_back_to_dm() -> None:
    """Сообщения в нажатии нет вовсе — остаётся личка того, кто нажал."""
    callback = _show(None)
    assert len(callback.bot.sent) == 1
    assert callback.bot.sent[0]["chat_id"] == 1419203590


@pytest.mark.parametrize("ok", [True, False], ids=["принято", "отказ"])
def test_delivery_never_raises(ok: bool) -> None:
    """Сбой доставки итога не имеет права уронить уже принятое решение."""
    refusal = TelegramBadRequest(method=None, message="message to edit not found")
    callback = _Callback(_Card(edit_error=refusal))

    async def refuse(*args, **kwargs):
        raise TelegramBadRequest(method=None, message="chat not found")

    callback.bot.send_message = refuse
    asyncio.run(review_ui.show_result(callback, ok, NOTE))  # не должно бросить
