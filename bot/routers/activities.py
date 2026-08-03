"""Заявки участников: мероприятие (в Афишу) и голосование (опрос в топик).

Обе заявки подаются в ЛС бота кнопками главного меню и уходят карточками
в админ-чат. Доступно только зарегистрированным.
"""

from html import escape

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import limits, texts
from bot.db.models import ActivityRequest, User, VoteRequest
from bot.keyboards.activity_kb import (
    act_review_kb,
    confirm_kb,
    form_cancel_kb,
    skip_step_kb,
    vote_anonymity_kb,
    vote_review_kb,
)
from bot.keyboards.common_kb import main_menu_kb
from bot.routers.common import send_start_screen
from bot.services import (
    activity_service,
    form_nav,
    input_guard,
    notification_service,
    scenario_service,
)
from bot.states.activity_states import ActivityForm, VoteForm

router = Router(name="activities")

_ANY_FORM = StateFilter(ActivityForm, VoteForm)


# --- Вопросы шагов ---
#
# Вопрос отделён от перехода: он нужен и когда человек идёт вперёд, и когда
# возвращается кнопкой «⬅️ Шаг назад». Состояние тут не трогается — этим
# занимается form_nav.


async def _ask_act_title(message: Message) -> None:
    await message.answer(
        texts.ACT_START.format(min=limits.ACT_TITLE_MIN, max=limits.ACT_TITLE_MAX),
        reply_markup=form_cancel_kb(),
    )


async def _ask_act_description(message: Message) -> None:
    await message.answer(
        texts.ACT_DESC_PROMPT.format(min=limits.ACT_DESC_MIN, max=limits.ACT_DESC_MAX),
        reply_markup=form_cancel_kb(),
    )


async def _ask_act_needs(message: Message) -> None:
    await message.answer(
        texts.ACT_NEEDS_PROMPT.format(min=limits.ACT_NEEDS_MIN, max=limits.ACT_NEEDS_MAX),
        reply_markup=form_cancel_kb(),
    )


async def _ask_act_organizers(message: Message) -> None:
    await message.answer(
        texts.ACT_ORGANIZERS_PROMPT.format(max=limits.ACT_ORGANIZERS_MAX, skip=texts.BTN.SKIP),
        reply_markup=skip_step_kb(),
    )


async def _ask_act_plan(message: Message) -> None:
    await message.answer(
        texts.ACT_PLAN_PROMPT.format(skip=texts.BTN.SKIP), reply_markup=skip_step_kb()
    )


async def _ask_act_chat(message: Message) -> None:
    await message.answer(
        texts.ACT_CHAT_PROMPT.format(skip=texts.BTN.SKIP), reply_markup=skip_step_kb()
    )


async def _ask_act_comment(message: Message) -> None:
    await message.answer(
        texts.ACT_COMMENT_PROMPT.format(max=limits.ACT_COMMENT_MAX, skip=texts.BTN.SKIP),
        reply_markup=skip_step_kb(),
    )


async def _ask_vote_question(message: Message) -> None:
    await message.answer(
        texts.VOTE_START.format(min=limits.VOTE_QUESTION_MIN, max=limits.VOTE_QUESTION_MAX),
        reply_markup=form_cancel_kb(),
    )


async def _ask_vote_options(message: Message) -> None:
    await message.answer(
        texts.VOTE_OPTIONS_PROMPT.format(
            min=limits.VOTE_OPTIONS_MIN,
            max=limits.VOTE_OPTIONS_MAX,
            opt_max=limits.VOTE_OPTION_MAX,
        ),
        reply_markup=form_cancel_kb(),
    )


async def _ask_vote_anonymity(message: Message) -> None:
    await message.answer(texts.VOTE_ANON_PROMPT, reply_markup=vote_anonymity_kb())


# Какой вопрос задать, вернувшись на шаг. Через lambda — сводки объявлены ниже
# по файлу, а имена в них разрешаются в момент вызова.
_ASK_BY_NAME = {
    ActivityForm.title.state: lambda m, st: _ask_act_title(m),
    ActivityForm.description.state: lambda m, st: _ask_act_description(m),
    ActivityForm.needs.state: lambda m, st: _ask_act_needs(m),
    ActivityForm.organizers.state: lambda m, st: _ask_act_organizers(m),
    ActivityForm.plan_url.state: lambda m, st: _ask_act_plan(m),
    ActivityForm.chat_url.state: lambda m, st: _ask_act_chat(m),
    ActivityForm.admin_comment.state: lambda m, st: _ask_act_comment(m),
    ActivityForm.confirm.state: lambda m, st: _act_show_confirm(m, st),
    VoteForm.question.state: lambda m, st: _ask_vote_question(m),
    VoteForm.options.state: lambda m, st: _ask_vote_options(m),
    VoteForm.anonymity.state: lambda m, st: _ask_vote_anonymity(m),
    VoteForm.confirm.state: lambda m, st: _vote_show_confirm(m, st),
}


# --- Вход (кнопки главного меню) ---


@router.message(
    F.chat.type == ChatType.PRIVATE, StateFilter(None), F.text == texts.BTN.ACT_NEW
)
async def start_activity_form(
    message: Message, state: FSMContext, db_user: User | None
) -> None:
    if db_user is None:
        await message.answer(texts.ACT_NOT_REGISTERED)
        return
    await form_nav.restart(state, ActivityForm.title)
    await _ask_act_title(message)


@router.message(
    F.chat.type == ChatType.PRIVATE, StateFilter(None), F.text == texts.BTN.VOTE_NEW
)
async def start_vote_form(message: Message, state: FSMContext, db_user: User | None) -> None:
    if db_user is None:
        await message.answer(texts.ACT_NOT_REGISTERED)
        return
    await form_nav.restart(state, VoteForm.question)
    await _ask_vote_question(message)


# --- Выходы: «🚫 Отмена» и спасательный /start ---


@router.message(_ANY_FORM, F.text == texts.BTN.REG_CANCEL)
async def form_cancel(message: Message, state: FSMContext, db_user: User | None) -> None:
    await state.clear()
    await message.answer(texts.ACT_CANCELLED, reply_markup=main_menu_kb(db_user))


@router.message(_ANY_FORM, F.text == texts.BTN.FORM_BACK)
async def form_step_back(message: Message, state: FSMContext) -> None:
    """Возврат на предыдущий вопрос заявки.

    Стоит выше обработчиков шагов: иначе «⬅️ Шаг назад» уехал бы в заявку
    названием мероприятия или вариантом ответа.
    """
    previous = await form_nav.back(state)
    if previous is None:
        await message.answer(texts.FORM_BACK_AT_START.format(cancel=texts.BTN.REG_CANCEL))
        return
    await message.answer(texts.FORM_BACK_DONE)
    await _ASK_BY_NAME[previous](message, state)


@router.message(_ANY_FORM, CommandStart())
async def form_start_over(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User | None
) -> None:
    await state.clear()
    await send_start_screen(message, session, db_user)


# --- Мероприятие: название → описание → ссылка → подтверждение ---


@router.message(ActivityForm.title, F.text, ~F.text.startswith("/"))
async def act_title(message: Message, state: FSMContext) -> None:
    title = message.text.strip()
    if not limits.ACT_TITLE_MIN <= len(title) <= limits.ACT_TITLE_MAX or "\n" in title:
        await message.answer(
            texts.ACT_TITLE_INVALID.format(min=limits.ACT_TITLE_MIN, max=limits.ACT_TITLE_MAX)
        )
        return
    await state.update_data(title=title)
    await form_nav.goto(state, ActivityForm.description)
    await _ask_act_description(message)


@router.message(ActivityForm.description, F.text, ~F.text.startswith("/"))
async def act_description(message: Message, state: FSMContext) -> None:
    description = message.text.strip()
    if not limits.ACT_DESC_MIN <= len(description) <= limits.ACT_DESC_MAX:
        await message.answer(
            texts.ACT_DESC_INVALID.format(min=limits.ACT_DESC_MIN, max=limits.ACT_DESC_MAX)
        )
        return
    await state.update_data(description=description)
    await form_nav.goto(state, ActivityForm.needs)
    await _ask_act_needs(message)


@router.message(ActivityForm.needs, F.text, ~F.text.startswith("/"))
async def act_needs(message: Message, state: FSMContext) -> None:
    """Что нужно для проведения. Шаг обязательный: пропустить нельзя.

    Свободный текст, а не набор полей: заранее не угадать, что понадобится —
    людям, деньгам, помещению и реквизиту здесь одинаково находится место.
    """
    needs = message.text.strip()
    if not limits.ACT_NEEDS_MIN <= len(needs) <= limits.ACT_NEEDS_MAX:
        await message.answer(
            texts.ACT_NEEDS_INVALID.format(min=limits.ACT_NEEDS_MIN, max=limits.ACT_NEEDS_MAX)
        )
        return
    await state.update_data(needs_text=needs)
    await form_nav.goto(state, ActivityForm.organizers)
    await _ask_act_organizers(message)


@router.message(ActivityForm.organizers, F.text, ~F.text.startswith("/"))
async def act_organizers(message: Message, state: FSMContext) -> None:
    raw = message.text.strip()
    if raw == texts.BTN.SKIP:
        await state.update_data(organizers_text=None)
    elif len(raw) > limits.ACT_ORGANIZERS_MAX:
        await message.answer(
            texts.ACT_ORGANIZERS_INVALID.format(
                max=limits.ACT_ORGANIZERS_MAX, skip=texts.BTN.SKIP
            )
        )
        return
    else:
        await state.update_data(organizers_text=raw)
    await form_nav.goto(state, ActivityForm.plan_url)
    await _ask_act_plan(message)


async def _act_take_url(message: Message, state: FSMContext, field: str) -> bool:
    """Общий шаг-ссылка: кладёт значение (или None при пропуске) в data[field]."""
    raw = message.text.strip()
    if raw == texts.BTN.SKIP:
        await state.update_data(**{field: None})
        return True
    if len(raw) > limits.ACT_URL_MAX:
        await message.answer(
            texts.ACT_URL_INVALID.format(max=limits.ACT_URL_MAX, skip=texts.BTN.SKIP)
        )
        return False
    await state.update_data(**{field: raw})
    return True


@router.message(ActivityForm.plan_url, F.text, ~F.text.startswith("/"))
async def act_plan_url(message: Message, state: FSMContext) -> None:
    if not await _act_take_url(message, state, "plan_url"):
        return
    await form_nav.goto(state, ActivityForm.chat_url)
    await _ask_act_chat(message)


@router.message(ActivityForm.chat_url, F.text, ~F.text.startswith("/"))
async def act_chat_url(message: Message, state: FSMContext) -> None:
    if not await _act_take_url(message, state, "chat_url"):
        return
    await form_nav.goto(state, ActivityForm.admin_comment)
    await _ask_act_comment(message)


async def _act_show_confirm(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await message.answer(
        texts.ACT_CONFIRM.format(
            title=escape(data["title"]),
            description=escape(data["description"]),
            details=activity_service.act_details(
                data.get("organizers_text"),
                data.get("plan_url"),
                data.get("chat_url"),
                data.get("admin_comment"),
                needs_text=data.get("needs_text"),
            ),
        ),
        reply_markup=confirm_kb(),
    )


@router.message(ActivityForm.admin_comment, F.text, ~F.text.startswith("/"))
async def act_admin_comment(message: Message, state: FSMContext) -> None:
    raw = message.text.strip()
    if raw == texts.BTN.SKIP:
        await state.update_data(admin_comment=None)
    elif len(raw) > limits.ACT_COMMENT_MAX:
        await message.answer(
            texts.ACT_COMMENT_INVALID.format(max=limits.ACT_COMMENT_MAX, skip=texts.BTN.SKIP)
        )
        return
    else:
        await state.update_data(admin_comment=raw)
    await form_nav.goto(state, ActivityForm.confirm)
    await _act_show_confirm(message, state)


@router.message(ActivityForm.confirm, F.text == texts.BTN.REG_SUBMIT)
async def act_submit(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    data = await state.get_data()
    await state.clear()
    request = ActivityRequest(
        tg_id=db_user.tg_id,
        title=data["title"],
        description=data["description"],
        needs_text=data.get("needs_text"),
        organizers_text=data.get("organizers_text"),
        plan_url=data.get("plan_url"),
        chat_url=data.get("chat_url"),
        admin_comment=data.get("admin_comment"),
    )
    session.add(request)
    await session.commit()
    await notification_service.send_admin_card(
        message.bot,
        activity_service.build_act_card(db_user, request),
        act_review_kb(str(request.request_id)),
    )
    await scenario_service.reply(message, session, "act_sent", main_menu_kb(db_user))


@router.message(ActivityForm.confirm, F.text == texts.BTN.REG_RESTART)
async def act_restart(message: Message, state: FSMContext) -> None:
    await form_nav.restart(state, ActivityForm.title)
    await _ask_act_title(message)


@router.message(ActivityForm.confirm, F.text, ~F.text.startswith("/"))
async def act_confirm_other(message: Message, state: FSMContext) -> None:
    await _act_show_confirm(message, state)


# --- Голосование: вопрос → варианты → подтверждение ---


@router.message(VoteForm.question, F.text, ~F.text.startswith("/"))
async def vote_question(message: Message, state: FSMContext) -> None:
    question = message.text.strip()
    if not limits.VOTE_QUESTION_MIN <= len(question) <= limits.VOTE_QUESTION_MAX:
        await message.answer(
            texts.VOTE_QUESTION_INVALID.format(
                min=limits.VOTE_QUESTION_MIN, max=limits.VOTE_QUESTION_MAX
            )
        )
        return
    await state.update_data(question=question)
    await form_nav.goto(state, VoteForm.options)
    await _ask_vote_options(message)


async def _vote_show_confirm(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    rows = "\n".join(
        texts.VOTE_OPTION_ROW.format(option=escape(option)) for option in data["options"]
    )
    await message.answer(
        texts.VOTE_CONFIRM.format(
            question=escape(data["question"]),
            options=rows,
            # .get: анкета могла начаться до появления шага (черновики живут в Redis
            # и переживают перезапуск) — считаем такой опрос анонимным, как раньше.
            anon=activity_service.anonymity_line(data.get("is_anonymous", True)),
        ),
        reply_markup=confirm_kb(),
    )


@router.message(VoteForm.options, F.text, ~F.text.startswith("/"))
async def vote_options(message: Message, state: FSMContext) -> None:
    options = activity_service.parse_vote_options(message.text)
    if options is None:
        await message.answer(
            texts.VOTE_OPTIONS_INVALID.format(
                min=limits.VOTE_OPTIONS_MIN,
                max=limits.VOTE_OPTIONS_MAX,
                opt_max=limits.VOTE_OPTION_MAX,
            )
        )
        return
    await state.update_data(options=options)
    await form_nav.goto(state, VoteForm.anonymity)
    await _ask_vote_anonymity(message)


@router.message(
    VoteForm.anonymity, F.text.in_({texts.BTN.VOTE_ANON_YES, texts.BTN.VOTE_ANON_NO})
)
async def vote_anonymity(message: Message, state: FSMContext) -> None:
    await state.update_data(is_anonymous=message.text == texts.BTN.VOTE_ANON_YES)
    await form_nav.goto(state, VoteForm.confirm)
    await _vote_show_confirm(message, state)


@router.message(VoteForm.anonymity, F.text, ~F.text.startswith("/"))
async def vote_anonymity_other(message: Message) -> None:
    await message.answer(texts.VOTE_ANON_USE_BUTTONS)


@router.message(VoteForm.confirm, F.text == texts.BTN.REG_SUBMIT)
async def vote_submit(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    data = await state.get_data()
    await state.clear()
    request = VoteRequest(
        tg_id=db_user.tg_id,
        question=data["question"],
        options=data["options"],
        is_anonymous=data.get("is_anonymous", True),
    )
    session.add(request)
    await session.commit()
    await notification_service.send_admin_card(
        message.bot,
        activity_service.build_vote_card(
            db_user, request.question, list(request.options), request.is_anonymous
        ),
        vote_review_kb(str(request.request_id)),
    )
    await scenario_service.reply(message, session, "vote_sent", main_menu_kb(db_user))


@router.message(VoteForm.confirm, F.text == texts.BTN.REG_RESTART)
async def vote_restart(message: Message, state: FSMContext) -> None:
    await form_nav.restart(state, VoteForm.question)
    await _ask_vote_question(message)


@router.message(VoteForm.confirm, F.text, ~F.text.startswith("/"))
async def vote_confirm_other(message: Message, state: FSMContext) -> None:
    await _vote_show_confirm(message, state)


# --- Последний рубеж обеих анкет ---


@router.message(_ANY_FORM)
async def form_unexpected(message: Message, state: FSMContext) -> None:
    """Всё, что не взял ни один шаг: фото, стикер, голосовое, файл, команда.

    Обязан стоять последним в роутере — иначе перехватил бы сами шаги. Молчание
    в ответ на присланную картинку выглядело как зависшая заявка, поэтому бот
    объясняет, что не подошло, и повторяет вопрос текущего шага.
    """
    await message.answer(input_guard.form_explain(message))
    ask = _ASK_BY_NAME.get(await state.get_state())
    if ask is not None:
        await ask(message, state)
