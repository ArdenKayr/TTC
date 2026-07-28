"""Сохранение оформления в редакторах контента и сценариев.

Telegram присылает оформление отдельно от букв (список пометок «с такого-то
символа по такой-то — премиум-эмодзи / жирный»). Проверяем, что помощник
переводит пометки обратно в HTML-теги, а не выбрасывает их.
"""

from datetime import datetime, timezone

import pytest
from aiogram.types import Chat, Message, MessageEntity, PhotoSize

from bot.services import content_service, scenario_service

_CHAT = Chat(id=1, type="private")
_DATE = datetime(2026, 7, 19, tzinfo=timezone.utc)


def _message(text: str, entities: list[MessageEntity] | None = None) -> Message:
    return Message(message_id=1, date=_DATE, chat=_CHAT, text=text, entities=entities)


def _photo_message(caption: str, entities: list[MessageEntity] | None = None) -> Message:
    return Message(
        message_id=1,
        date=_DATE,
        chat=_CHAT,
        photo=[PhotoSize(file_id="f", file_unique_id="u", width=1, height=1)],
        caption=caption,
        caption_entities=entities,
    )


def test_premium_emoji_survives():
    """Премиум-эмодзи — пометка custom_emoji; она должна стать тегом tg-emoji."""
    message = _message(
        "\U0001F44D готово",
        [MessageEntity(type="custom_emoji", offset=0, length=2, custom_emoji_id="5368324170671202286")],
    )
    assert content_service.formatted_text(message) == (
        '<tg-emoji emoji-id="5368324170671202286">\U0001F44D</tg-emoji> готово'
    )


def test_bold_and_link_survive():
    message = _message(
        "жирный и ссылка",
        [
            MessageEntity(type="bold", offset=0, length=6),
            MessageEntity(type="text_link", offset=9, length=6, url="https://example.com"),
        ],
    )
    assert content_service.formatted_text(message) == (
        '<b>жирный</b> и <a href="https://example.com">ссылка</a>'
    )


def test_premium_emoji_in_caption_survives():
    """У файла оформление лежит в отдельном списке — его тоже надо забрать."""
    message = _photo_message(
        "\U0001F44D подпись",
        [MessageEntity(type="custom_emoji", offset=0, length=2, custom_emoji_id="777")],
    )
    assert content_service.formatted_text(message) == (
        '<tg-emoji emoji-id="777">\U0001F44D</tg-emoji> подпись'
    )


def test_angle_brackets_are_escaped():
    """Раньше «<» уходил в базу сырым и ломал отправку — теперь экранируется."""
    assert content_service.formatted_text(_message("1 < 2 & 3")) == "1 &lt; 2 &amp; 3"


def test_plain_text_unchanged_and_trimmed():
    assert content_service.formatted_text(_message("  привет  ")) == "привет"


def test_placeholders_survive_formatting():
    """Подстановки сценариев не должны пострадать от перевода в HTML."""
    message = _message(
        "Мероприятие {title} одобрено",
        [MessageEntity(type="bold", offset=12, length=7)],  # «{title}» целиком
    )
    text = content_service.formatted_text(message)
    assert text == "Мероприятие <b>{title}</b> одобрено"
    assert scenario_service.validate_template(text)
    assert not scenario_service.has_split_placeholder(text)
    assert text.format_map({"title": "Поход"}) == "Мероприятие <b>Поход</b> одобрено"


def test_placeholder_split_by_formatting_is_rejected():
    """Жирным выделили слово без скобок — подстановка сломана, текст не принимаем.

    Формально скобки парные, поэтому обычная проверка это пропускает, а человек
    получил бы сырое «{<b>title</b>}» вместо названия.
    """
    message = _message(
        "Мероприятие {title} одобрено",
        [MessageEntity(type="bold", offset=13, length=5)],  # только слово «title»
    )
    text = content_service.formatted_text(message)
    assert text == "Мероприятие {<b>title</b>} одобрено"
    assert scenario_service.validate_template(text)  # скобки парные — старая проверка молчит
    assert scenario_service.has_split_placeholder(text)  # новая ловит


def test_normal_text_with_tags_outside_placeholders_is_allowed():
    assert not scenario_service.has_split_placeholder("<b>Привет</b>, {name}!")
    assert not scenario_service.has_split_placeholder("Без подстановок <i>вообще</i>")


@pytest.mark.parametrize("raw", ["<b>руками</b>", "просто < текст"])
def test_hand_typed_tags_become_visible_text(raw):
    """Осознанная смена поведения: теги, набранные руками, теперь показываются как текст."""
    assert "&lt;" in content_service.formatted_text(_message(raw))
