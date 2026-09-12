"""Анкета не остаётся на шаге, вопрос которого человек не увидел.

Написано по записи №13 в журнале боевых ошибок (9 сентября 2026, 23:01 МСК):
человек нажал «📅 Мероприятие», отправка первого вопроса не уложилась в
отведённое время — и он остался на шаге «название» при пустом экране. Дальше
любое его слово бот принял бы за название мероприятия, а повторное нажатие
кнопки сделало бы названием саму надпись на ней.

Проверяется не текст ошибки, а свойство: после падения человек там же, где
был до нажатия. И отдельно — что у этого правила есть граница: завершённую
анкету назад не откатывают, иначе человек подал бы вторую такую же заявку.
"""

from __future__ import annotations

import asyncio

import pytest

from bot.middlewares.form_guard import FormGuardMiddleware
from bot.services import form_nav
from bot.states.activity_states import ActivityForm
from bot.states.registration_states import RegistrationForm


class _State:
    """Минимальный FSMContext: состояние и данные, как у настоящего."""

    def __init__(self) -> None:
        self._state: str | None = None
        self._data: dict = {}

    async def get_state(self):
        return self._state

    async def set_state(self, state):
        self._state = state.state if hasattr(state, "state") else state

    async def get_data(self):
        return dict(self._data)

    async def update_data(self, **kwargs):
        self._data.update(kwargs)
        return dict(self._data)


class _SendFailed(Exception):
    """Вопрос до человека не дошёл — то самое, что случилось 9 сентября."""


async def _pass_through(handler, state) -> object:
    """Прогнать обработчик через слой, как это делает диспетчер."""
    return await FormGuardMiddleware()(handler, object(), {"state": state})


# --- Главное свойство ---


def test_failed_form_start_does_not_leave_the_person_inside() -> None:
    """Анкета не началась — значит, человек снаружи, как и был."""

    async def scenario():
        state = _State()

        async def handler(event, data):
            await form_nav.restart(state, ActivityForm.title)
            raise _SendFailed  # вопрос не ушёл

        with pytest.raises(_SendFailed):
            await _pass_through(handler, state)

        assert await state.get_state() is None, (
            "Человек остался внутри анкеты, не увидев ни одного вопроса, — "
            "следующее его слово бот примет за название мероприятия."
        )

    asyncio.run(scenario())


def test_failed_step_returns_to_the_question_on_screen() -> None:
    """Шаг не состоялся — человек остаётся у вопроса, который видит."""

    async def scenario():
        state = _State()
        await form_nav.restart(state, RegistrationForm.nick)
        await form_nav.goto(state, RegistrationForm.university_search)

        async def handler(event, data):
            await form_nav.goto(state, RegistrationForm.search_feedback)
            raise _SendFailed

        with pytest.raises(_SendFailed):
            await _pass_through(handler, state)

        assert await state.get_state() == RegistrationForm.university_search.state

    asyncio.run(scenario())


def test_rewind_cleans_the_trail_so_back_still_works() -> None:
    """После отката «⬅️ Шаг назад» ведёт назад, а не на текущий шаг.

    goto() кладёт прежний шаг в историю до отправки вопроса. Не убрать эту
    запись — и кнопка «назад» приведёт человека туда, где он и так стоит.
    """

    async def scenario():
        state = _State()
        await form_nav.restart(state, RegistrationForm.nick)
        await form_nav.goto(state, RegistrationForm.university_search)

        async def handler(event, data):
            await form_nav.goto(state, RegistrationForm.search_feedback)
            raise _SendFailed

        with pytest.raises(_SendFailed):
            await _pass_through(handler, state)

        assert await form_nav.back(state) == RegistrationForm.nick.state

    asyncio.run(scenario())


# --- Граница правила ---


def test_finished_form_is_never_rewound() -> None:
    """Анкету, которую обработчик завершил, назад не возвращают.

    За таким падением уже могла остаться запись в базе. Вернуть человека к
    кнопке отправки — значит получить вторую такую же заявку; лучше молчание.
    """

    async def scenario():
        state = _State()
        await form_nav.restart(state, RegistrationForm.confirm)

        async def handler(event, data):
            await state.set_state(None)  # заявка отправлена и записана
            raise _SendFailed  # а вот «спасибо» человеку уже не дошло

        with pytest.raises(_SendFailed):
            await _pass_through(handler, state)

        assert await state.get_state() is None, (
            "Человека вернули к кнопке «Отправить» — он подаст вторую заявку."
        )

    asyncio.run(scenario())


def test_successful_handler_is_left_alone() -> None:
    """Пока всё хорошо, слой не вмешивается."""

    async def scenario():
        state = _State()

        async def handler(event, data):
            await form_nav.restart(state, ActivityForm.title)
            return "ответ обработчика"

        assert await _pass_through(handler, state) == "ответ обработчика"
        assert await state.get_state() == ActivityForm.title.state

    asyncio.run(scenario())


def test_original_error_survives_a_broken_rewind() -> None:
    """Если и откат не удался, человек узнаёт об исходной беде, а не о нём."""

    class _Brittle(_State):
        async def get_data(self):
            raise RuntimeError("хранилище недоступно")

    async def scenario():
        state = _Brittle()

        async def handler(event, data):
            await state.set_state(ActivityForm.title)
            raise _SendFailed

        with pytest.raises(_SendFailed):
            await _pass_through(handler, state)

    asyncio.run(scenario())


def test_updates_outside_any_form_pass_through() -> None:
    """Без анкеты слою нечего стеречь — он просто пропускает апдейт."""

    async def scenario():
        async def handler(event, data):
            return "готово"

        assert await FormGuardMiddleware()(handler, object(), {}) == "готово"

    asyncio.run(scenario())
