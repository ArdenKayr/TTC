from datetime import date, datetime
from html import escape

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import limits, texts
from bot.db.repositories import alias_suggestion_repo, university_repo
from bot.keyboards.callback_data import (
    AliasDoneCB,
    RegFormCB,
    SearchFeedbackCB,
    StartCB,
    UniversityNewCB,
    UniversityNoneCB,
    UniversityPickCB,
)
from bot.keyboards.registration_kb import (
    alias_done_kb,
    confirm_kb,
    search_feedback_kb,
    university_prompt_kb,
    university_results_kb,
)
from bot.services import registration_service, university_service
from bot.states.registration_states import RegistrationForm

router = Router(name="registration")


def _valid_line(text: str, min_len: int, max_len: int) -> bool:
    return min_len <= len(text) <= max_len and "\n" not in text


def _valid_link(link: str) -> bool:
    if not (4 <= len(link) <= limits.UNI_LINK_MAX) or any(ch.isspace() for ch in link):
        return False
    return link.startswith(("http://", "https://", "t.me/", "@")) or "." in link


async def _ask_group(message: Message, state: FSMContext) -> None:
    await state.set_state(RegistrationForm.university_group)
    await message.answer(texts.REG_GROUP_PROMPT)


# --- Вход в анкету ---


@router.message(Command("register"), F.chat.type == ChatType.PRIVATE)
async def cmd_register(message: Message, session: AsyncSession, state: FSMContext) -> None:
    error = await registration_service.check_can_apply(session, message.from_user.id)
    if error:
        await message.answer(error)
        return
    await state.clear()
    await state.set_state(RegistrationForm.nick)
    await message.answer(texts.REG_START)


@router.callback_query(StartCB.filter(F.action == "register"))
async def cb_start_register(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    error = await registration_service.check_can_apply(session, callback.from_user.id)
    if error:
        await callback.answer(error, show_alert=True)
        return
    await state.clear()
    await state.set_state(RegistrationForm.nick)
    await callback.message.answer(texts.REG_START)
    await callback.answer()


# --- Имя/ник ---


@router.message(RegistrationForm.nick, F.text)
async def form_nick(message: Message, state: FSMContext) -> None:
    nick = message.text.strip()
    if not _valid_line(nick, limits.NICK_MIN, limits.NICK_MAX):
        await message.answer(
            texts.REG_NAME_INVALID.format(min=limits.NICK_MIN, max=limits.NICK_MAX)
        )
        return
    await state.update_data(nick=nick)
    await state.set_state(RegistrationForm.university_search)
    await message.answer(texts.REG_UNI_PROMPT, reply_markup=university_prompt_kb())


# --- Поиск вуза ---


@router.message(RegistrationForm.university_search, F.text)
async def form_university_search(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    query = message.text.strip()
    await state.update_data(university_query=query)
    results = await university_repo.search(session, query)
    text = texts.REG_UNI_CHOOSE if results else texts.REG_UNI_NOT_FOUND
    await message.answer(text, reply_markup=university_results_kb(results))


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
    await state.update_data(
        uni_mode="picked",
        university_id=university.university_id,
        university_name=university.canonical_name,
    )
    await state.set_state(RegistrationForm.search_feedback)
    await callback.message.edit_text(
        texts.REG_UNI_PICKED.format(university=escape(university.canonical_name))
    )
    await callback.message.answer(texts.REG_UNI_FEEDBACK, reply_markup=search_feedback_kb())
    await callback.answer()


# --- «Удобно ли было искать?» ---


@router.callback_query(RegistrationForm.search_feedback, SearchFeedbackCB.filter(F.action == "yes"))
async def form_feedback_yes(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await _ask_group(callback.message, state)
    await callback.answer()


@router.callback_query(RegistrationForm.search_feedback, SearchFeedbackCB.filter(F.action == "no"))
async def form_feedback_no(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(RegistrationForm.alias_suggest)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        texts.REG_ALIAS_PROMPT.format(
            university=escape(data["university_name"]),
            limit=limits.ALIAS_SUGGESTIONS_PER_USER,
            done=texts.BTN.ALIAS_DONE,
        ),
        reply_markup=alias_done_kb(),
    )
    await callback.answer()


@router.message(RegistrationForm.alias_suggest, F.text)
async def form_alias_suggest(message: Message, session: AsyncSession, state: FSMContext) -> None:
    alias = message.text.strip()
    if not _valid_line(alias, limits.ALIAS_MIN, limits.ALIAS_MAX):
        await message.answer(
            texts.REG_ALIAS_INVALID.format(
                min=limits.ALIAS_MIN, max=limits.ALIAS_MAX, done=texts.BTN.ALIAS_DONE
            ),
            reply_markup=alias_done_kb(),
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
        await _ask_group(message, state)
        return
    university = await university_repo.get(session, data["university_id"])
    if university is None:
        await _ask_group(message, state)
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
        ),
        reply_markup=None if sent >= limits.ALIAS_SUGGESTIONS_PER_USER else alias_done_kb(),
    )
    if sent >= limits.ALIAS_SUGGESTIONS_PER_USER:
        await message.answer(
            texts.REG_ALIAS_LIMIT_REACHED.format(limit=limits.ALIAS_SUGGESTIONS_PER_USER)
        )
        await _ask_group(message, state)


@router.callback_query(RegistrationForm.alias_suggest, AliasDoneCB.filter())
async def form_alias_done(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await _ask_group(callback.message, state)
    await callback.answer()


# --- «Не учусь в вузе СПб» ---


@router.callback_query(RegistrationForm.university_search, UniversityNoneCB.filter())
async def form_no_university(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(
        uni_mode="none", university_id=None, university_name=None, university_group=None
    )
    await state.set_state(RegistrationForm.no_uni_about)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        texts.REG_NO_UNI_INFO.format(min=limits.ABOUT_MIN, limit=limits.ABOUT_MAX)
    )
    await callback.answer()


@router.message(RegistrationForm.no_uni_about, F.text)
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
    await state.set_state(RegistrationForm.birth_date)
    await message.answer(texts.REG_BIRTH_PROMPT)


# --- Заявка на новый вуз ---


@router.callback_query(RegistrationForm.university_search, UniversityNewCB.filter())
async def form_university_new(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(uni_mode="new")
    await state.set_state(RegistrationForm.uni_new_name)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(texts.REG_UNI_NEW_PROMPT)
    await callback.answer()


@router.message(RegistrationForm.uni_new_name, F.text)
async def form_uni_new_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if not _valid_line(name, 5, 255):
        await message.answer(texts.REG_UNI_NEW_TOO_SHORT)
        return
    await state.update_data(new_uni_name=name, new_uni_aliases=[])
    await state.set_state(RegistrationForm.uni_new_aliases)
    await message.answer(
        texts.REG_UNI_NEW_ALIASES_PROMPT.format(
            limit=limits.NEW_UNI_ALIASES_MAX, done=texts.BTN.ALIAS_DONE
        ),
        reply_markup=alias_done_kb(),
    )


@router.message(RegistrationForm.uni_new_aliases, F.text)
async def form_uni_new_alias(message: Message, state: FSMContext) -> None:
    alias = message.text.strip()
    if not _valid_line(alias, limits.ALIAS_MIN, limits.ALIAS_MAX):
        await message.answer(
            texts.REG_ALIAS_INVALID.format(
                min=limits.ALIAS_MIN, max=limits.ALIAS_MAX, done=texts.BTN.ALIAS_DONE
            ),
            reply_markup=alias_done_kb(),
        )
        return
    data = await state.get_data()
    aliases: list[str] = data.get("new_uni_aliases", [])
    if alias.lower() in (a.lower() for a in aliases):
        await message.answer(texts.REG_UNI_NEW_ALIAS_DUP, reply_markup=alias_done_kb())
        return
    aliases.append(alias)
    await state.update_data(new_uni_aliases=aliases)
    done = len(aliases) >= limits.NEW_UNI_ALIASES_MAX
    await message.answer(
        texts.REG_UNI_NEW_ALIAS_ACCEPTED.format(
            alias=escape(alias), n=len(aliases), limit=limits.NEW_UNI_ALIASES_MAX
        ),
        reply_markup=None if done else alias_done_kb(),
    )
    if done:
        await state.set_state(RegistrationForm.uni_new_link)
        await message.answer(texts.REG_UNI_NEW_LINK_PROMPT)


@router.callback_query(RegistrationForm.uni_new_aliases, AliasDoneCB.filter())
async def form_uni_new_aliases_done(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.set_state(RegistrationForm.uni_new_link)
    await callback.message.answer(texts.REG_UNI_NEW_LINK_PROMPT)
    await callback.answer()


@router.message(RegistrationForm.uni_new_link, F.text)
async def form_uni_new_link(message: Message, state: FSMContext) -> None:
    link = message.text.strip()
    if not _valid_link(link):
        await message.answer(texts.REG_UNI_NEW_LINK_INVALID)
        return
    await state.update_data(new_uni_link=link)
    await _ask_group(message, state)


# --- Группа и дата рождения ---


@router.message(RegistrationForm.university_group, F.text)
async def form_university_group(message: Message, state: FSMContext) -> None:
    group = message.text.strip()
    if not group or len(group) > 50:
        await message.answer(texts.REG_GROUP_INVALID)
        return
    await state.update_data(university_group=group)
    await state.set_state(RegistrationForm.birth_date)
    await message.answer(texts.REG_BIRTH_PROMPT)


@router.message(RegistrationForm.birth_date, F.text)
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
    await state.set_state(RegistrationForm.confirm)
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
    lines.append(texts.SUM_BIRTH.format(birth_date=birth_date.strftime("%d.%m.%Y")))

    await message.answer(
        texts.REG_SUMMARY_HEADER + "\n\n" + "\n".join(lines), reply_markup=confirm_kb()
    )


# --- Подтверждение ---


@router.callback_query(RegistrationForm.confirm, RegFormCB.filter())
async def form_confirm(
    callback: CallbackQuery,
    callback_data: RegFormCB,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if callback_data.action == "cancel":
        await state.clear()
        await callback.message.edit_text(texts.REG_CANCELLED)
        await callback.answer()
        return
    if callback_data.action == "restart":
        await state.clear()
        await state.set_state(RegistrationForm.nick)
        await callback.message.edit_text(texts.REG_RESTARTED)
        await callback.answer()
        return

    error = await registration_service.check_can_apply(session, callback.from_user.id)
    if error:
        await state.clear()
        await callback.message.edit_text(error)
        await callback.answer()
        return
    data = await state.get_data()
    request = await registration_service.submit_request(
        session, callback.bot, callback.from_user, data
    )
    await state.clear()
    submitted = (
        texts.REG_SUBMITTED_TWO_STEP
        if request.university_request_id is not None
        else texts.REG_SUBMITTED
    )
    await callback.message.edit_text(submitted)
    await callback.answer()
