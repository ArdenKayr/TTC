from aiogram.fsm.state import State, StatesGroup


class ReferralForm(StatesGroup):
    """Создание ссылки-приглашения: название, а у суперадмина — ещё и кому."""

    title = State()
    owner = State()
