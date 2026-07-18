from aiogram.fsm.state import State, StatesGroup


class ProfileForm(StatesGroup):
    edit_nick = State()
    edit_group = State()
    edit_birth = State()
    edit_about = State()


class ReportForm(StatesGroup):
    text = State()  # одно сообщение с сутью репорта
