from aiogram.fsm.state import State, StatesGroup


class ReviewEditForm(StatesGroup):
    """Админ исправляет данные заявки перед решением (убирает опечатки)."""

    university_request = State()  # ждём исправленные название + варианты
    alias_suggestion = State()  # ждём исправленный вариант поиска
