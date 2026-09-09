"""Как карточка-заявка отвечает админу на нажатие кнопки.

Telegram даёт на подтверждение нажатия несколько секунд: не успел — нажатие
протухает, и ответить по нему уже нельзя («query is too old»). Разбор заявки
в эти секунды не укладывается: бот успевает сходить в Telegram за
инвайт-ссылкой, написать человеку в личку, опубликовать пост в группе. Стоит
связи с Telegram подтормозить — и разбор проходит, а админ видит зависшую
кнопку и ошибку вместо ответа.

Так и случилось на бою 28.08.2026 (записи №3–5 в журнале): заявку одобрили,
кнопка не отозвалась, админ нажал второй раз — и оба нажатия закончились
ошибкой, хотя человек был принят с первого.

Поэтому здесь два раздельных шага: сначала подтверждаем нажатие, до всякой
работы, а её итог показываем уже в самой карточке — она никуда не денется
и её видят все админы, в отличие от всплывающего окна.

Сама карточка при этом — ненадёжная опора, и это выяснилось 09.09.2026,
когда разбор мероприятий стал выглядеть сломанным. Дописать итог в неё
получается не всегда, причём по трём разным причинам:

- **у карточки мероприятия есть обложка.** Это не текстовое сообщение, а
  фотография с подписью, и правится у неё подпись: правка текста в такой
  карточке Telegram запрещена вовсе;
- **подпись вмещает 1024 символа.** Итог, дописанный к длинной заявке, в
  этот предел может и не влезть;
- **старую карточку Telegram присылает без содержимого.** В нажатии кнопки
  вместо сообщения приходит заглушка `InaccessibleMessage` — в ней есть
  только номер чата и номер сообщения, а текста нет: дописывать не к чему.

Ни одна из этих причин не отменяет решения админа — оно к этому моменту уже
принято и применено. Поэтому итог здесь доставляется любой ценой: не вышло
дописать в карточку — приходит отдельным сообщением рядом с ней.
"""

from contextlib import suppress

from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, InaccessibleMessage, Message, ReplyParameters


async def ack(callback: CallbackQuery) -> None:
    """Снять «часики» с кнопки — первым делом, ещё до работы.

    Подтверждение ничего не сообщает человеку, поэтому его потеря не повод
    бросать разбор заявки: связь до Telegram может отвалиться как раз в эту
    секунду, а решение админа при этом уже принято.
    """
    with suppress(TelegramAPIError):
        await callback.answer()


async def _append(card: Message, note: str) -> None:
    """Дописать итог в карточку и убрать кнопки.

    У карточки с обложкой правится подпись, у обычной — текст. `html_text`
    одинаково отдаёт и то и другое, а вот метод правки для них разный.
    """
    text = card.html_text + f"\n\n{note}"
    if card.text is None and card.caption is not None:
        await card.edit_caption(caption=text, reply_markup=None)
        return
    await card.edit_text(text, reply_markup=None)


async def _note_beside(callback: CallbackQuery, note: str) -> None:
    """Итог отдельным сообщением рядом с карточкой — когда в неё не вышло.

    Отправляется ответом на карточку: в чате с темами это единственный способ
    попасть в ту же тему, не зная её номера — у заглушки старого сообщения
    номера темы нет. Карточку могли и удалить, поэтому Telegram отдельно
    разрешается отправить сообщение без привязки к ней.
    """
    card = callback.message
    if card is None:
        # Нажатие пришло вообще без сообщения — остаётся личка самого админа.
        with suppress(TelegramAPIError):
            await callback.bot.send_message(callback.from_user.id, note)
        return
    with suppress(TelegramAPIError):
        await callback.bot.send_message(
            card.chat.id,
            note,
            reply_parameters=ReplyParameters(
                message_id=card.message_id, allow_sending_without_reply=True
            ),
        )


async def show_result(callback: CallbackQuery, ok: bool, note: str) -> None:
    """Показать итог разбора в карточке.

    Если разобрать не вышло (заявку уже закрыл другой админ, её вовсе нет),
    карточку не трогаем — там уже чужой итог, и затирать его нельзя. Тогда
    объяснение приходит ответом на карточку.
    """
    card = callback.message
    if card is None or isinstance(card, InaccessibleMessage):
        # Карточка слишком старая: Telegram прислал заглушку без текста.
        await _note_beside(callback, note)
        return
    try:
        if ok:
            await _append(card, note)
        else:
            await card.reply(note)
    except TelegramAPIError:
        await _note_beside(callback, note)
