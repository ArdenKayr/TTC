from aiogram.fsm.state import State, StatesGroup


class RegistrationForm(StatesGroup):
    nick = State()  # имя/ник — как обращаться
    university_search = State()  # ввод запроса и выбор вуза из списка
    search_feedback = State()  # «удобно ли было искать?»
    alias_suggest = State()  # присылает варианты поиска для выбранного вуза
    no_uni_about = State()  # не учится в вузе СПб — рассказ о себе
    uni_new_name = State()  # новый вуз: полное название
    uni_new_aliases = State()  # новый вуз: сокращения
    uni_new_link = State()  # новый вуз: ссылка для проверки
    university_group = State()
    birth_date = State()
    confirm = State()
