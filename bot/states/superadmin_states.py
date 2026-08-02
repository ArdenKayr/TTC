from aiogram.fsm.state import State, StatesGroup


class SuperadminForm(StatesGroup):
    user_ref = State()  # ввод tg_id или @username в разделе «👤 Пользователи»
    ban_reason = State()  # причина бана (её видит забаненный, она же идёт в журнал)
