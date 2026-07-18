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
    vote_review_kb,
)
from bot.keyboards.common_kb import main_menu_kb
from bot.routers.common import send_start_screen
from bot.services import activity_service, notification_service
from bot.states.activity_states import ActivityForm, VoteForm

router = Router(name="activities")

_ANY_FORM = StateFilter(ActivityForm, VoteForm)


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
    await state.set_state(ActivityForm.title)
    await message.answer(
        texts.ACT_START.format(min=limits.ACT_TITLE_MIN, max=limits.ACT_TITLE_MAX),
        reply_markup=form_cancel_kb(),
    )


@router.message(
    F.chat.type == ChatType.PRIVATE, StateFilter(None), F.text == texts.BTN.VOTE_NEW
)
async def start_vote_form(message: Message, state: FSMContext, db_user: User | None) -> None:
    if db_user is None:
        await message.answer(texts.ACT_NOT_REGISTERED)
        return
    await state.set_state(VoteForm.question)
    await message.answer(
        texts.VOTE_START.format(min=limits.VOTE_QUESTION_MIN, max=limits.VOTE_QUESTION_MAX),
        reply_markup=form_cancel_kb(),
    )


# --- Выходы: «🚫 Отмена» и спасательный /start ---


@router.message(_ANY_FORM, F.text == texts.BTN.REG_CANCEL)
async def form_cancel(message: Message, state: FSMContext, db_user: User | None) -> None:
    await state.clear()
    await message.answer(texts.ACT_CANCELLED, reply_markup=main_menu_kb(db_user))


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
    await state.set_state(ActivityForm.description)
    await message.answer(
        texts.ACT_DESC_PROMPT.format(min=limits.ACT_DESC_MIN, max=limits.ACT_DESC_MAX)
    )


@router.message(ActivityForm.description, F.text, ~F.text.startswith("/"))
async def act_description(message: Message, state: FSMContext) -> None:
    description = message.text.strip()
    if not limits.ACT_DESC_MIN <= len(description) <= limits.ACT_DESC_MAX:
        await message.answer(
            texts.ACT_DESC_INVALID.format(min=limits.ACT_DESC_MIN, max=limits.ACT_DESC_MAX)
        )
        return
    await state.update_data(description=description)
    await state.set_state(ActivityForm.organizers)
    await message.answer(
        texts.ACT_ORGANIZERS_PROMPT.format(max=limits.ACT_ORGANIZERS_MAX, skip=texts.BTN.SKIP),
        reply_markup=skip_step_kb(),
    )


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
    await state.set_state(ActivityForm.plan_url)
    await message.answer(texts.ACT_PLAN_PROMPT.format(skip=texts.BTN.SKIP))


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
    await state.set_state(ActivityForm.chat_url)
    await message.answer(texts.ACT_CHAT_PROMPT.format(skip=texts.BTN.SKIP))


@router.message(ActivityForm.chat_url, F.text, ~F.text.startswith("/"))
async def act_chat_url(message: Message, state: FSMContext) -> None:
    if not await _act_take_url(message, state, "chat_url"):
        return
    await state.set_state(ActivityForm.admin_comment)
    await message.answer(
        texts.ACT_COMMENT_PROMPT.format(max=limits.ACT_COMMENT_MAX, skip=texts.BTN.SKIP)
    )


async def _act_show_confirm(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(ActivityForm.confirm)
    await message.answer(
        texts.ACT_CONFIRM.format(
            title=escape(data["title"]),
            description=escape(data["description"]),
            details=activity_service.act_details(
                data.get("organizers_text"),
                data.get("plan_url"),
                data.get("chat_url"),
                data.get("admin_comment"),
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
    await message.answer(texts.ACT_SENT, reply_markup=main_menu_kb(db_user))


@router.message(ActivityForm.confirm, F.text == texts.BTN.REG_RESTART)
async def act_restart(message: Message, state: FSMContext) -> None:
    await state.set_state(ActivityForm.title)
    await message.answer(
        texts.ACT_START.format(min=limits.ACT_TITLE_MIN, max=limits.ACT_TITLE_MAX),
        reply_markup=form_cancel_kb(),
    )


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
    await state.set_state(VoteForm.options)
    await message.answer(
        texts.VOTE_OPTIONS_PROMPT.format(
            min=limits.VOTE_OPTIONS_MIN,
            max=limits.VOTE_OPTIONS_MAX,
            opt_max=limits.VOTE_OPTION_MAX,
        )
    )


async def _vote_show_confirm(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    rows = "\n".join(
        texts.VOTE_OPTION_ROW.format(option=escape(option)) for option in data["options"]
    )
    await state.set_state(VoteForm.confirm)
    await message.answer(
        texts.VOTE_CONFIRM.format(question=escape(data["question"]), options=rows),
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
    await _vote_show_confirm(message, state)


@router.message(VoteForm.confirm, F.text == texts.BTN.REG_SUBMIT)
async def vote_submit(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    data = await state.get_data()
    await state.clear()
    request = VoteRequest(tg_id=db_user.tg_id, question=data["question"], options=data["options"])
    session.add(request)
    await session.commit()
    await notification_service.send_admin_card(
        message.bot,
        activity_service.build_vote_card(db_user, request.question, list(request.options)),
        vote_review_kb(str(request.request_id)),
    )
    await message.answer(texts.VOTE_SENT, reply_markup=main_menu_kb(db_user))


@router.message(VoteForm.confirm, F.text == texts.BTN.REG_RESTART)
async def vote_restart(message: Message, state: FSMContext) -> None:
    await state.set_state(VoteForm.question)
    await message.answer(
        texts.VOTE_START.format(min=limits.VOTE_QUESTION_MIN, max=limits.VOTE_QUESTION_MAX),
        reply_markup=form_cancel_kb(),
    )


@router.message(VoteForm.confirm, F.text, ~F.text.startswith("/"))
async def vote_confirm_other(message: Message, state: FSMContext) -> None:
    await _vote_show_confirm(message, state)
