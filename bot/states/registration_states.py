from aiogram.fsm.state import State, StatesGroup


class RegistrationForm(StatesGroup):
    full_name = State()
    university_search = State()
    university_new_name = State()
    university_group = State()
    birth_date = State()
    confirm = State()
