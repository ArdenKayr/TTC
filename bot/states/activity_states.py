from aiogram.fsm.state import State, StatesGroup


class ActivityForm(StatesGroup):
    title = State()
    description = State()
    extra_url = State()  # ссылка или «Без ссылки»
    confirm = State()


class VoteForm(StatesGroup):
    question = State()
    options = State()  # варианты одним сообщением, по строке на вариант
    confirm = State()
