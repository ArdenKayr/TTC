from aiogram.fsm.state import State, StatesGroup


class ContentEditForm(StatesGroup):
    waiting = State()


class ScenarioEditForm(StatesGroup):
    waiting = State()  # ожидание нового текста/файла для сценария (data: key)


class CrudForm(StatesGroup):
    value = State()  # ввод нового значения поля (data: t, pk, i, page)
    create = State()  # последовательный ввод полей новой записи (data: t, idx, values)
