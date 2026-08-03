"""Шаг назад в анкетах.

Раньше ошибка на любом шаге стоила всей анкеты: выбрал не тот вуз — отменяй
и заполняй заново, с ника. Теперь у каждого шага есть «⬅️ Шаг назад»: бот
возвращает предыдущий вопрос, а всё введённое до него остаётся на месте.

**Почему история шагов, а не их порядок.** Анкета регистрации ветвится: из
шага с вузом можно уйти в «моего вуза нет» (три шага заявки на вуз), в «не
учусь в вузе СПб» (рассказ о себе) или выбрать вуз из списка (и тогда будет
вопрос про удобство поиска). Порядок объявления состояний этих развилок не
знает — «предыдущим» для шага с группой окажется то один шаг, то другой.
Поэтому бот запоминает пройденный путь: goto() кладёт текущий шаг в стопку,
back() снимает верхний. Возврат всегда ведёт туда, откуда человек пришёл на
самом деле.

Хранится стопка в тех же данных формы, что и ответы, — значит переживает
перезапуск бота (FSM лежит в Redis) и очищается вместе с анкетой.
"""

from __future__ import annotations

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State

# С подчёркивания — чтобы не путалось с ответами человека в тех же данных.
HISTORY_KEY = "_steps"


async def goto(state: FSMContext, step: State) -> None:
    """Перейти на следующий шаг, запомнив текущий.

    Все переходы внутри анкет идут через эту функцию: прямой set_state потерял
    бы след, и «назад» увёл бы не туда. За этим следит tests/test_form_back.py.
    """
    current = await state.get_state()
    if current is not None:
        data = await state.get_data()
        history = [*data.get(HISTORY_KEY, []), current]
        await state.update_data(**{HISTORY_KEY: history})
    await state.set_state(step)


async def back(state: FSMContext) -> str | None:
    """Вернуться на предыдущий шаг. None — если возвращаться некуда."""
    data = await state.get_data()
    history = list(data.get(HISTORY_KEY, []))
    if not history:
        return None
    previous = history.pop()
    await state.update_data(**{HISTORY_KEY: history})
    await state.set_state(previous)
    return previous


async def restart(state: FSMContext, step: State) -> None:
    """Начать анкету заново: путь стирается, ответы тоже."""
    await state.update_data(**{HISTORY_KEY: []})
    await state.set_state(step)
