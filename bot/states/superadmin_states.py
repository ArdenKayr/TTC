from aiogram.fsm.state import State, StatesGroup


class SuperadminForm(StatesGroup):
    user_ref = State()  # ввод tg_id или @username для «Манипуляции с пользователем»
