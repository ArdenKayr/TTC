"""Рассылка обновления: что именно получает участник.

Когда выходит обновление, владелец пишет пост, и бот рассылает его в личку
всем участникам. Человеку при этом важно знать не только «что нового», но и
где это потом искать, — поэтому к личному сообщению приписывается путь до
раздела с архивом обновлений.

В сам архив приписка не идёт: там она повторялась бы у каждой записи, а
человек и так уже стоит в этом разделе, когда его читает.
"""

from __future__ import annotations

from bot import texts
from bot.services.update_service import build_broadcast, build_entry


def test_entry_starts_with_the_date_header():
    entry = build_entry("Починили кнопку.")
    assert entry.startswith("📢")
    assert "Починили кнопку." in entry


def test_broadcast_tells_where_to_find_updates():
    """В личке человек узнаёт, в каком разделе лежат все обновления."""
    message = build_broadcast(build_entry("Починили кнопку."))
    assert texts.BTN.INFO in message
    assert texts.BTN.INFO_UPDATES in message


def test_archive_entry_has_no_footer():
    """Иначе путь до раздела повторялся бы у каждой записи архива."""
    entry = build_entry("Починили кнопку.")
    assert texts.BTN.INFO_UPDATES not in entry


def test_broadcast_keeps_the_text_intact():
    """Приписка добавляется в конец и ничего не съедает."""
    entry = build_entry("Починили кнопку.")
    assert build_broadcast(entry).startswith(entry)


def test_footer_names_real_buttons():
    """Кнопки переименуют — подсказка должна догнать их сама, а не устареть."""
    buttons = {
        value
        for name, value in vars(texts.BTN).items()
        if not name.startswith("_") and isinstance(value, str)
    }
    message = build_broadcast(build_entry("текст"))
    named = message.rsplit("\n\n", 1)[-1]
    mentioned = {part.strip(".") for part in named.split("«") if "»" in part}
    mentioned = {part.split("»")[0] for part in mentioned}
    assert mentioned <= buttons, f"в подсказке названия, которых нет среди кнопок: {mentioned - buttons}"
