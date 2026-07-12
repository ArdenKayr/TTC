from aiogram.fsm.state import State, StatesGroup


class ContentEditForm(StatesGroup):
    waiting = State()
