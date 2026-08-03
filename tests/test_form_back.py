"""«⬅️ Шаг назад» в анкетах.

Раньше ошибка на любом шаге стоила всей анкеты: выбрал не тот вуз — отменяй и
заполняй заново, с ника. Теперь бот запоминает пройденный путь и по кнопке
возвращает предыдущий вопрос, сохранив всё, что человек уже ответил.

Почему именно путь, а не порядок состояний: анкета регистрации ветвится. Из
шага с вузом уходят в «моего вуза нет» (три шага заявки), в «не учусь в вузе
СПб» (рассказ о себе) или выбирают вуз из списка (и тогда будет вопрос про
удобство поиска). «Предыдущим» для шага с группой оказывается то один шаг, то
другой — угадать по объявлению состояний нельзя.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from bot.services import form_nav
from bot.states.activity_states import ActivityForm, VoteForm
from bot.states.registration_states import RegistrationForm

ROOT = Path(__file__).resolve().parent.parent


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


def test_back_returns_to_the_previous_step():
    async def scenario():
        state = _State()
        await form_nav.restart(state, RegistrationForm.nick)
        await form_nav.goto(state, RegistrationForm.university_search)
        await form_nav.goto(state, RegistrationForm.search_feedback)

        assert await form_nav.back(state) == RegistrationForm.university_search.state
        assert await state.get_state() == RegistrationForm.university_search.state

    asyncio.run(scenario())


def test_back_follows_the_branch_actually_taken():
    """Главное свойство: возврат ведёт туда, откуда человек пришёл.

    К вопросу про группу приходят тремя дорогами. Здесь — через «не учусь в
    вузе СПб», и назад должно вести на рассказ о себе, а не на «удобно ли было
    искать», который в этой ветке не показывали.
    """

    async def scenario():
        state = _State()
        await form_nav.restart(state, RegistrationForm.nick)
        await form_nav.goto(state, RegistrationForm.university_search)
        await form_nav.goto(state, RegistrationForm.no_uni_about)
        await form_nav.goto(state, RegistrationForm.birth_date)

        assert await form_nav.back(state) == RegistrationForm.no_uni_about.state

    asyncio.run(scenario())


def test_answers_survive_the_return():
    """Возврат переспрашивает шаг, а не стирает анкету."""

    async def scenario():
        state = _State()
        await form_nav.restart(state, RegistrationForm.nick)
        await state.update_data(nick="Черешня")
        await form_nav.goto(state, RegistrationForm.university_search)
        await form_nav.back(state)

        assert (await state.get_data())["nick"] == "Черешня"

    asyncio.run(scenario())


def test_no_way_back_from_the_first_step():
    """На первом вопросе возвращаться некуда — бот скажет об этом."""

    async def scenario():
        state = _State()
        await form_nav.restart(state, RegistrationForm.nick)
        assert await form_nav.back(state) is None

    asyncio.run(scenario())


def test_walking_back_and_forth_does_not_pile_up():
    """Вернулись и снова пошли вперёд — путь не задваивается."""

    async def scenario():
        state = _State()
        await form_nav.restart(state, ActivityForm.title)
        await form_nav.goto(state, ActivityForm.description)
        await form_nav.goto(state, ActivityForm.needs)
        await form_nav.back(state)
        await form_nav.goto(state, ActivityForm.needs)

        assert (await state.get_data())[form_nav.HISTORY_KEY] == [
            ActivityForm.title.state,
            ActivityForm.description.state,
        ]

    asyncio.run(scenario())


def test_restart_forgets_the_path():
    """«Заполнить заново» начинает с чистого листа, иначе «назад» уведёт в старое."""

    async def scenario():
        state = _State()
        await form_nav.restart(state, VoteForm.question)
        await form_nav.goto(state, VoteForm.options)
        await form_nav.restart(state, VoteForm.question)

        assert await form_nav.back(state) is None

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "router", ["bot/routers/registration.py", "bot/routers/activities.py"]
)
def test_forms_never_switch_steps_behind_the_history(router):
    """Сторож: переходы в анкетах идут только через form_nav.

    Прямой set_state не оставил бы следа в пути, и «Шаг назад» увёл бы не туда
    — молча и только в одной ветке, то есть заметили бы это нескоро.
    """
    source = (ROOT / router).read_text(encoding="utf-8")
    assert "set_state" not in source, (
        f"в {router} остался прямой set_state — переход должен идти через "
        "form_nav.goto/restart, иначе путь для «Шаг назад» потеряется"
    )


@pytest.mark.parametrize(
    "router, form",
    [
        ("bot/routers/registration.py", RegistrationForm),
        ("bot/routers/activities.py", ActivityForm),
        ("bot/routers/activities.py", VoteForm),
    ],
)
def test_every_step_knows_how_to_ask_itself(router, form):
    """У каждого шага анкеты есть свой вопрос в реестре возврата.

    Забыть шаг в реестре — значит уронить бота ровно в тот момент, когда
    человек попробует вернуться именно на него.
    """
    source = (ROOT / router).read_text(encoding="utf-8")
    registry = source.split("_ASK_BY_NAME", 1)[1] if "_ASK_BY_NAME" in source else ""
    if router.endswith("registration.py"):
        registry = source.split("_ASK_STEP = {", 1)[1].split("}", 1)[0]
    else:
        registry = source.split("_ASK_BY_NAME = {", 1)[1].split("}", 1)[0]
    for name in form.__state_names__:
        step = name.split(":")[-1]
        assert re.search(rf"\.{step}\b", registry), (
            f"шаг «{step}» ({form.__name__}) не описан в реестре возврата {router}"
        )
