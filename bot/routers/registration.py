from datetime import date, datetime
from html import escape

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import limits, texts
from bot.db.models import University, User
from bot.db.repositories import alias_suggestion_repo, university_repo
from bot.keyboards.callback_data import (
    NoopCB,
    StartCB,
    UniPageCB,
    UniShowAllCB,
    UniversityPickCB,
)
from bot.keyboards.common_kb import main_menu_kb
from bot.keyboards.registration_kb import (
    alias_step_kb,
    confirm_kb,
    form_cancel_kb,
    search_feedback_kb,
    uni_menu_kb,
    university_browser_kb,
)
from bot.routers.common import send_start_screen
from bot.services import (
    form_nav,
    input_guard,
    registration_service,
    scenario_service,
    university_service,
)
from bot.states.registration_states import RegistrationForm

router = Router(name="registration")


def _valid_line(text: str, min_len: int, max_len: int) -> bool:
    return min_len <= len(text) <= max_len and "\n" not in text


def _valid_link(link: str) -> bool:
    if not (4 <= len(link) <= limits.UNI_LINK_MAX) or any(ch.isspace() for ch in link):
        return False
    return link.startswith(("http://", "https://", "t.me/", "@")) or "." in link


async def _begin_form(message: Message, state: FSMContext) -> None:
    await state.clear()
    await form_nav.restart(state, RegistrationForm.nick)
    await _ask_nick(message)


# --- Вопросы шагов ---
#
# Каждый шаг умеет задать свой вопрос отдельно от перехода на него: то же самое
# нужно и когда человек идёт вперёд, и когда возвращается кнопкой «Шаг назад».
# Состояние здесь не трогается — это дело form_nav.goto/back.


async def _ask_nick(message: Message) -> None:
    await message.answer(texts.REG_START, reply_markup=form_cancel_kb())


async def _render_browser(session: AsyncSession, query: str | None, page: int):
    """Текст и кнопки страницы листаемого списка вузов.

    Полные названия — нумерованным списком в тексте (в кнопку длинное название
    не помещается), на кнопках — только номера.
    """
    items, total = await university_repo.browse(
        session, query, limit=limits.UNI_PAGE_SIZE, offset=page * limits.UNI_PAGE_SIZE
    )
    pages = max(1, -(-total // limits.UNI_PAGE_SIZE))  # округление вверх
    if total == 0:
        text = (
            texts.REG_UNI_BROWSER_EMPTY.format(query=escape(query))
            if query
            else texts.REG_UNI_BROWSER_NO_DATA
        )
    else:
        header = (
            texts.REG_UNI_BROWSER_FILTERED.format(
                query=escape(query), page=page + 1, pages=pages
            )
            if query
            else texts.REG_UNI_BROWSER_ALL.format(page=page + 1, pages=pages)
        )
        lines = [
            texts.REG_UNI_LIST_ITEM.format(
                n=page * limits.UNI_PAGE_SIZE + i + 1, name=escape(uni.canonical_name)
            )
            for i, uni in enumerate(items)
        ]
        text = header + "\n\n" + "\n".join(lines)
    return text, university_browser_kb(items, page, pages, filtered=bool(query))


async def _send_browser(
    message: Message, state: FSMContext, session: AsyncSession, query: str | None
) -> None:
    """Шлёт новую страницу списка, снимая кнопки со старой (чтобы не путали)."""
    data = await state.get_data()
    old_mid = data.get("browser_mid")
    if old_mid:
        try:
            await message.bot.edit_message_reply_markup(
                chat_id=message.chat.id, message_id=old_mid, reply_markup=None
            )
        except TelegramAPIError:
            pass
    text, kb = await _render_browser(session, query, page=0)
    sent = await message.answer(text, reply_markup=kb)
    await state.update_data(university_query=query, browser_mid=sent.message_id)


async def _ask_university(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    await message.answer(texts.REG_UNI_PROMPT, reply_markup=uni_menu_kb())
    await _send_browser(message, state, session, query=None)


async def _ask_feedback(message: Message) -> None:
    await message.answer(texts.REG_UNI_FEEDBACK, reply_markup=search_feedback_kb())


async def _ask_alias(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await message.answer(
        texts.REG_ALIAS_PROMPT.format(
            university=escape(data["university_name"]),
            limit=limits.ALIAS_SUGGESTIONS_PER_USER,
            done=texts.BTN.ALIAS_DONE,
        ),
        reply_markup=alias_step_kb(),
    )


async def _ask_about(message: Message) -> None:
    await message.answer(
        texts.REG_NO_UNI_INFO.format(min=limits.ABOUT_MIN, limit=limits.ABOUT_MAX),
        reply_markup=form_cancel_kb(),
    )


async def _ask_uni_new_name(message: Message) -> None:
    await message.answer(texts.REG_UNI_NEW_PROMPT, reply_markup=form_cancel_kb())


async def _ask_uni_new_aliases(message: Message) -> None:
    await message.answer(
        texts.REG_UNI_NEW_ALIASES_PROMPT.format(
            limit=limits.NEW_UNI_ALIASES_MAX, done=texts.BTN.ALIAS_DONE
        ),
        reply_markup=alias_step_kb(),
    )


async def _ask_uni_new_link(message: Message) -> None:
    await message.answer(texts.REG_UNI_NEW_LINK_PROMPT, reply_markup=form_cancel_kb())


async def _ask_group(message: Message) -> None:
    await message.answer(texts.REG_GROUP_PROMPT, reply_markup=form_cancel_kb())


async def _goto_group(message: Message, state: FSMContext) -> None:
    """К шагу группы приходят из трёх разных веток — переход общий для всех."""
    await form_nav.goto(state, RegistrationForm.university_group)
    await _ask_group(message)


async def _ask_birth(message: Message) -> None:
    await message.answer(texts.REG_BIRTH_PROMPT, reply_markup=form_cancel_kb())


async def _ask_confirm(message: Message, state: FSMContext) -> None:
    """Сводка анкеты перед отправкой."""
    data = await state.get_data()
    lines = [texts.SUM_NICK.format(nick=escape(data["nick"]))]
    mode = data.get("uni_mode", "picked")
    if mode == "new":
        lines.append(texts.SUM_UNI_NEW.format(university=escape(data["new_uni_name"])))
    elif mode == "none":
        lines.append(texts.SUM_UNI_NONE)
    else:
        lines.append(texts.SUM_UNI.format(university=escape(data["university_name"])))
    if data.get("university_group"):
        lines.append(texts.SUM_GROUP.format(group=escape(data["university_group"])))
    if data.get("about_text"):
        lines.append(texts.SUM_ABOUT.format(about=escape(data["about_text"])))
    birth_date = date.fromisoformat(data["birth_date"])
    lines.append(texts.SUM_BIRTH.format(birth_date=birth_date.strftime("%d.%m.%Y")))
    await message.answer(
        texts.REG_SUMMARY_HEADER + "\n\n" + "\n".join(lines), reply_markup=confirm_kb()
    )


# Какой вопрос задать, вернувшись на шаг. Ключ — имя состояния, как его хранит
# FSM. Без реестра «Шаг назад» пришлось бы разбирать в одном обработчике
# лестницу из десятка if — и забыть в ней ветку было бы вопросом времени.
_ASK_STEP = {
    RegistrationForm.nick: lambda m, st, se: _ask_nick(m),
    RegistrationForm.university_search: lambda m, st, se: _ask_university(m, st, se),
    RegistrationForm.search_feedback: lambda m, st, se: _ask_feedback(m),
    RegistrationForm.alias_suggest: lambda m, st, se: _ask_alias(m, st),
    RegistrationForm.no_uni_about: lambda m, st, se: _ask_about(m),
    RegistrationForm.uni_new_name: lambda m, st, se: _ask_uni_new_name(m),
    RegistrationForm.uni_new_aliases: lambda m, st, se: _ask_uni_new_aliases(m),
    RegistrationForm.uni_new_link: lambda m, st, se: _ask_uni_new_link(m),
    RegistrationForm.university_group: lambda m, st, se: _ask_group(m),
    RegistrationForm.birth_date: lambda m, st, se: _ask_birth(m),
    RegistrationForm.confirm: lambda m, st, se: _ask_confirm(m, st),
}
_ASK_BY_NAME = {step.state: ask for step, ask in _ASK_STEP.items()}


async def _university_chosen(
    message: Message, state: FSMContext, university: University
) -> None:
    await state.update_data(
        uni_mode="picked",
        university_id=university.university_id,
        university_name=university.canonical_name,
    )
    await form_nav.goto(state, RegistrationForm.search_feedback)
    await message.answer(
        texts.REG_UNI_PICKED.format(university=escape(university.canonical_name))
    )
    await _ask_feedback(message)


# --- Вход в анкету ---


@router.message(
    F.chat.type == ChatType.PRIVATE, StateFilter(None), F.text == texts.BTN.START_REGISTER
)
async def msg_menu_register(message: Message, session: AsyncSession, state: FSMContext) -> None:
    error = await registration_service.check_can_apply(session, message.from_user.id)
    if error:
        await message.answer(error)
        return
    await _begin_form(message, state)


@router.callback_query(StartCB.filter(F.action == "register"))
async def cb_start_register(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    """Кнопка «Регистрация» под старыми приветственными сообщениями."""
    error = await registration_service.check_can_apply(session, callback.from_user.id)
    if error:
        await callback.answer(error, show_alert=True)
        return
    await _begin_form(callback.message, state)
    await callback.answer()


# --- Выходы из анкеты: «🚫 Отмена» и спасательный /start ---


@router.message(StateFilter(RegistrationForm), F.text == texts.BTN.REG_CANCEL)
async def form_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.REG_CANCELLED, reply_markup=main_menu_kb(None))


@router.message(StateFilter(RegistrationForm), F.text == texts.BTN.FORM_BACK)
async def form_step_back(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    """Возврат на предыдущий вопрос анкеты.

    Стоит выше обработчиков шагов: иначе «⬅️ Шаг назад» записался бы как ответ —
    ником, названием вуза или номером группы.
    """
    previous = await form_nav.back(state)
    if previous is None:
        await message.answer(texts.FORM_BACK_AT_START.format(cancel=texts.BTN.REG_CANCEL))
        return
    await message.answer(texts.FORM_BACK_DONE)
    await _ASK_BY_NAME[previous](message, state, session)


@router.message(StateFilter(RegistrationForm), CommandStart())
async def form_start_over(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User | None
) -> None:
    """/start посреди анкеты выводит на главный экран (анкета сбрасывается)."""
    await state.clear()
    await send_start_screen(message, session, db_user)


# --- Имя/ник ---


@router.message(RegistrationForm.nick, F.text, ~F.text.startswith("/"))
async def form_nick(message: Message, session: AsyncSession, state: FSMContext) -> None:
    nick = message.text.strip()
    if not _valid_line(nick, limits.NICK_MIN, limits.NICK_MAX):
        await message.answer(
            texts.REG_NAME_INVALID.format(min=limits.NICK_MIN, max=limits.NICK_MAX)
        )
        return
    await state.update_data(nick=nick)
    await form_nav.goto(state, RegistrationForm.university_search)
    await _ask_university(message, state, session)


# --- Шаг вуза: кнопки меню (доступны сразу) ---


@router.message(RegistrationForm.university_search, F.text == texts.BTN.UNI_NOT_LISTED)
async def form_university_new(message: Message, state: FSMContext) -> None:
    await state.update_data(uni_mode="new")
    await form_nav.goto(state, RegistrationForm.uni_new_name)
    await _ask_uni_new_name(message)


@router.message(RegistrationForm.university_search, F.text == texts.BTN.UNI_NONE)
async def form_no_university(message: Message, state: FSMContext) -> None:
    await state.update_data(
        uni_mode="none", university_id=None, university_name=None, university_group=None
    )
    await form_nav.goto(state, RegistrationForm.no_uni_about)
    await _ask_about(message)


# --- Шаг вуза: листаемый список, сужающийся по запросу ---


@router.message(RegistrationForm.university_search, F.text, ~F.text.startswith("/"))
async def form_university_search(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    query = message.text.strip()
    university = await university_repo.find_by_exact_name(session, query)
    if university is not None:
        await _university_chosen(message, state, university)
        return
    await _send_browser(message, state, session, query=query)


@router.callback_query(RegistrationForm.university_search, UniPageCB.filter())
async def form_university_page(
    callback: CallbackQuery,
    callback_data: UniPageCB,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    """Стрелки ⬅️➡️: перелистываем список, редактируя то же сообщение."""
    data = await state.get_data()
    text, kb = await _render_browser(
        session, data.get("university_query"), page=max(0, callback_data.page)
    )
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except TelegramAPIError:
        pass  # страница не изменилась — просто гасим «часики» на кнопке
    await callback.answer()


@router.callback_query(NoopCB.filter())
async def cb_noop(callback: CallbackQuery) -> None:
    """Декоративные кнопки (счётчик страниц): просто гасим «часики»."""
    await callback.answer()


@router.callback_query(RegistrationForm.university_search, UniShowAllCB.filter())
async def form_university_show_all(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    await state.update_data(university_query=None)
    text, kb = await _render_browser(session, None, page=0)
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except TelegramAPIError:
        pass
    await callback.answer()


@router.callback_query(RegistrationForm.university_search, UniversityPickCB.filter())
async def form_university_pick(
    callback: CallbackQuery,
    callback_data: UniversityPickCB,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    university = await university_repo.get(session, callback_data.university_id)
    if university is None:
        await callback.answer(texts.REG_UNI_GONE, show_alert=True)
        return
    await callback.message.edit_reply_markup(reply_markup=None)
    await _university_chosen(callback.message, state, university)
    await callback.answer()


# --- «Удобно ли было искать?» ---


@router.message(RegistrationForm.search_feedback, F.text == texts.BTN.UNI_FB_YES)
async def form_feedback_yes(message: Message, state: FSMContext) -> None:
    await _goto_group(message, state)


@router.message(RegistrationForm.search_feedback, F.text == texts.BTN.UNI_FB_NO)
async def form_feedback_no(message: Message, state: FSMContext) -> None:
    await form_nav.goto(state, RegistrationForm.alias_suggest)
    await _ask_alias(message, state)


@router.message(RegistrationForm.search_feedback, F.text, ~F.text.startswith("/"))
async def form_feedback_other(message: Message) -> None:
    await message.answer(texts.REG_USE_BUTTONS)


# --- Свои варианты поиска для выбранного вуза ---


@router.message(RegistrationForm.alias_suggest, F.text == texts.BTN.ALIAS_DONE)
async def form_alias_done(message: Message, state: FSMContext) -> None:
    await _goto_group(message, state)


@router.message(RegistrationForm.alias_suggest, F.text, ~F.text.startswith("/"))
async def form_alias_suggest(message: Message, session: AsyncSession, state: FSMContext) -> None:
    alias = message.text.strip()
    if not _valid_line(alias, limits.ALIAS_MIN, limits.ALIAS_MAX):
        await message.answer(
            texts.REG_ALIAS_INVALID.format(
                min=limits.ALIAS_MIN, max=limits.ALIAS_MAX, done=texts.BTN.ALIAS_DONE
            )
        )
        return
    data = await state.get_data()
    sent = await alias_suggestion_repo.count_for_user(
        session, message.from_user.id, data["university_id"]
    )
    if sent >= limits.ALIAS_SUGGESTIONS_PER_USER:
        await message.answer(
            texts.REG_ALIAS_LIMIT_REACHED.format(limit=limits.ALIAS_SUGGESTIONS_PER_USER)
        )
        await _goto_group(message, state)
        return
    university = await university_repo.get(session, data["university_id"])
    if university is None:
        await _goto_group(message, state)
        return
    await university_service.submit_alias_suggestion(
        session,
        message.bot,
        tg_id=message.from_user.id,
        applicant_name=data["nick"],
        applicant_username=message.from_user.username,
        university=university,
        alias_text=alias,
    )
    sent += 1
    await message.answer(
        texts.REG_ALIAS_ACCEPTED.format(
            alias=escape(alias), n=sent, limit=limits.ALIAS_SUGGESTIONS_PER_USER
        )
    )
    if sent >= limits.ALIAS_SUGGESTIONS_PER_USER:
        await message.answer(
            texts.REG_ALIAS_LIMIT_REACHED.format(limit=limits.ALIAS_SUGGESTIONS_PER_USER)
        )
        await _goto_group(message, state)


# --- «Не учусь в вузе СПб» — рассказ о себе ---


@router.message(RegistrationForm.no_uni_about, F.text, ~F.text.startswith("/"))
async def form_about(message: Message, state: FSMContext) -> None:
    about = message.text.strip()
    if len(about) < limits.ABOUT_MIN:
        await message.answer(texts.REG_ABOUT_TOO_SHORT.format(min=limits.ABOUT_MIN))
        return
    if len(about) > limits.ABOUT_MAX:
        await message.answer(
            texts.REG_ABOUT_TOO_LONG.format(limit=limits.ABOUT_MAX, length=len(about))
        )
        return
    await state.update_data(about_text=about)
    await form_nav.goto(state, RegistrationForm.birth_date)
    await _ask_birth(message)


# --- Заявка на новый вуз ---


@router.message(RegistrationForm.uni_new_name, F.text, ~F.text.startswith("/"))
async def form_uni_new_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if not _valid_line(name, 5, 255):
        await message.answer(texts.REG_UNI_NEW_TOO_SHORT)
        return
    await state.update_data(new_uni_name=name, new_uni_aliases=[])
    await form_nav.goto(state, RegistrationForm.uni_new_aliases)
    await _ask_uni_new_aliases(message)


@router.message(RegistrationForm.uni_new_aliases, F.text == texts.BTN.ALIAS_DONE)
async def form_uni_new_aliases_done(message: Message, state: FSMContext) -> None:
    await form_nav.goto(state, RegistrationForm.uni_new_link)
    await _ask_uni_new_link(message)


@router.message(RegistrationForm.uni_new_aliases, F.text, ~F.text.startswith("/"))
async def form_uni_new_alias(message: Message, state: FSMContext) -> None:
    alias = message.text.strip()
    if not _valid_line(alias, limits.ALIAS_MIN, limits.ALIAS_MAX):
        await message.answer(
            texts.REG_ALIAS_INVALID.format(
                min=limits.ALIAS_MIN, max=limits.ALIAS_MAX, done=texts.BTN.ALIAS_DONE
            )
        )
        return
    data = await state.get_data()
    aliases: list[str] = data.get("new_uni_aliases", [])
    if alias.lower() in (a.lower() for a in aliases):
        await message.answer(texts.REG_UNI_NEW_ALIAS_DUP)
        return
    aliases.append(alias)
    await state.update_data(new_uni_aliases=aliases)
    await message.answer(
        texts.REG_UNI_NEW_ALIAS_ACCEPTED.format(
            alias=escape(alias), n=len(aliases), limit=limits.NEW_UNI_ALIASES_MAX
        )
    )
    if len(aliases) >= limits.NEW_UNI_ALIASES_MAX:
        await form_nav.goto(state, RegistrationForm.uni_new_link)
        await _ask_uni_new_link(message)


@router.message(RegistrationForm.uni_new_link, F.text, ~F.text.startswith("/"))
async def form_uni_new_link(message: Message, state: FSMContext) -> None:
    link = message.text.strip()
    if not _valid_link(link):
        await message.answer(texts.REG_UNI_NEW_LINK_INVALID)
        return
    await state.update_data(new_uni_link=link)
    await _goto_group(message, state)


# --- Группа и дата рождения ---


@router.message(RegistrationForm.university_group, F.text, ~F.text.startswith("/"))
async def form_university_group(message: Message, state: FSMContext) -> None:
    group = message.text.strip()
    if not group or len(group) > 50:
        await message.answer(texts.REG_GROUP_INVALID)
        return
    await state.update_data(university_group=group)
    await form_nav.goto(state, RegistrationForm.birth_date)
    await _ask_birth(message)


@router.message(RegistrationForm.birth_date, F.text, ~F.text.startswith("/"))
async def form_birth_date(message: Message, state: FSMContext) -> None:
    try:
        birth_date = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
    except ValueError:
        await message.answer(texts.REG_BIRTH_INVALID)
        return
    age = (date.today() - birth_date).days // 365
    if age < 14 or age > 100:
        await message.answer(texts.REG_BIRTH_IMPLAUSIBLE)
        return
    await state.update_data(birth_date=birth_date.isoformat())
    await form_nav.goto(state, RegistrationForm.confirm)
    await _ask_confirm(message, state)


# --- Подтверждение (кнопки меню; «Отмена» ловится общим обработчиком выше) ---


@router.message(RegistrationForm.confirm, F.text == texts.BTN.REG_RESTART)
async def form_restart(message: Message, state: FSMContext) -> None:
    await state.clear()
    await form_nav.restart(state, RegistrationForm.nick)
    await message.answer(texts.REG_RESTARTED, reply_markup=form_cancel_kb())


@router.message(RegistrationForm.confirm, F.text == texts.BTN.REG_SUBMIT)
async def form_submit(message: Message, session: AsyncSession, state: FSMContext) -> None:
    error = await registration_service.check_can_apply(session, message.from_user.id)
    if error:
        await state.clear()
        await message.answer(error, reply_markup=main_menu_kb(None))
        return
    data = await state.get_data()
    request = await registration_service.submit_request(
        session, message.bot, message.from_user, data
    )
    await state.clear()
    submitted_key = (
        "reg_submitted_two_step" if request.university_request_id is not None else "reg_submitted"
    )
    await scenario_service.reply(message, session, submitted_key, main_menu_kb(None))


@router.message(RegistrationForm.confirm, F.text, ~F.text.startswith("/"))
async def form_confirm_other(message: Message) -> None:
    await message.answer(texts.REG_USE_BUTTONS)


# --- Последний рубеж анкеты ---


@router.message(StateFilter(RegistrationForm))
async def form_unexpected(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    """Всё, что не взял ни один шаг: фото, стикер, голосовое, файл, команда.

    Обязан стоять последним в роутере — иначе перехватил бы сами шаги.
    Раньше такое сообщение проваливалось в пустоту, и анкета выглядела
    зависшей: человек не знал, ждать ответа или начинать заново. Теперь бот
    объясняет, что не подошло, и повторяет вопрос, на котором человек стоит.
    """
    await message.answer(input_guard.form_explain(message))
    ask = _ASK_BY_NAME.get(await state.get_state())
    if ask is not None:
        await ask(message, state, session)
