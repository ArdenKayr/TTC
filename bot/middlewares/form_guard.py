"""Человек внутри анкеты — значит, он видел её вопрос.

Порядок во всех обработчиках один: сначала выставить шаг анкеты, потом
отправить вопрос. Пока Telegram отвечает, это незаметно. Но если отправка не
удалась — связь моргнула, — шаг остаётся выставленным, а на экране у человека
не появилось ничего. Дальше любое его слово бот молча примет за ответ на
вопрос, которого тот не видел.

Так и вышло 9 сентября (запись №13 в журнале ошибок): человек нажал
«📅 Мероприятие», первый вопрос анкеты не уложился в отведённое время, и
человек остался на шаге «название» при пустом экране. Нажми он ту же кнопку
ещё раз — названием мероприятия стала бы надпись на кнопке.

Слой возвращает шаг назад, если обработчик упал: не получилось — значит, не
произошло. Чинить порядок в двадцати четырёх местах смысла нет — двадцать
пятая анкета завела бы ловушку заново.

**Одно исключение — завершённые анкеты.** Если обработчик успел обнулить шаг
(«заявка отправлена»), возврат не делается: за таким падением уже могла
остаться запись в базе, и человек, возвращённый к кнопке отправки, подал бы
вторую такую же заявку. Молчание бота здесь — меньшее зло, чем дубль.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import TelegramObject

from bot.services import form_nav


class FormGuardMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        state: FSMContext | None = data.get("state")
        if state is None:
            return await handler(event, data)

        before = await state.get_state()
        try:
            return await handler(event, data)
        except Exception:
            await _rewind(state, before)
            raise


async def _rewind(state: FSMContext, before: str | None) -> None:
    """Вернуть анкету туда, где она была до неудавшегося шага.

    Возврат — дело необязательное: если и он не удастся, человеку важнее
    получить карточку об исходной ошибке, чем вторую о неудачном откате.
    """
    try:
        after = await state.get_state()
        if after is None or after == before:
            return
        await form_nav.rewind(state, before)
    except Exception:  # noqa: BLE001 — откат не должен подменять исходную ошибку
        return
