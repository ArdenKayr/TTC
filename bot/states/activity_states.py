from aiogram.fsm.state import State, StatesGroup


class ActivityForm(StatesGroup):
    title = State()
    description = State()
    needs = State()  # что нужно для проведения: люди, деньги, помещение
    organizers = State()  # кто проводит, @ники (можно пропустить)
    plan_url = State()  # ссылка на план реализации (можно пропустить)
    chat_url = State()  # ссылка на беседу мероприятия (можно пропустить)
    admin_comment = State()  # комментарий админам (можно пропустить)
    confirm = State()


class VoteForm(StatesGroup):
    question = State()
    options = State()  # варианты одним сообщением, по строке на вариант
    anonymity = State()  # анонимный опрос или видно, кто как ответил
    confirm = State()
