from aiogram.fsm.state import State, StatesGroup


class PermAdminForm(StatesGroup):
    """Панель /admins: ожидание ввода от полного админа."""

    group_name = State()  # название новой группы прав
    person_lookup = State()  # tg_id или @username человека