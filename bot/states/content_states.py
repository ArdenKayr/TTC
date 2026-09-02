from aiogram.fsm.state import State, StatesGroup


class ContentEditForm(StatesGroup):
    waiting = State()


class ScenarioEditForm(StatesGroup):
    waiting = State()  # ожидание нового текста/файла для сценария (data: key)


class CrudForm(StatesGroup):
    value = State()  # ввод нового значения поля (data: t, pk, i, page)
    create = State()  # последовательный ввод полей новой записи (data: t, idx, values)


class UpdatePostForm(StatesGroup):
    waiting = State()  # ожидание текста/файла обновления
    confirm = State()  # подтверждение рассылки (data: text, file_id, file_type)


class BroadcastForm(StatesGroup):
    waiting = State()  # ожидание текста/файла письма всем
    confirm = State()  # подтверждение рассылки (data: text, file_id, file_type)
