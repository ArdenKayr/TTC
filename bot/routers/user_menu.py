"""Главное меню зарегистрированного: «Информация», «Репорт», «Админство».

Каждая кнопка «Информации» показывает редактируемый блок контента
(/content); «Админские регламенты» видят только суперадмины и владелец.
Режим «Админство» меняет только меню — команды работают всегда.
"""

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import limits, texts
from bot.db.models import User
from bot.db.repositories import report_repo
from bot.enums import CLOSED_REPORT_STATUSES, UserRole
from bot.keyboards.activity_kb import form_cancel_kb
from bot.keyboards.callback_data import ReportAnswerCB
from bot.keyboards.common_kb import (
    admin_panel_kb,
    has_admin_powers,
    info_menu_kb,
    main_menu_kb,
)
from bot.routers.common import send_start_screen
from bot.services import (
    content_service,
    input_guard,
    permission_service,
    report_service,
    scenario_service,
)
from bot.states.profile_states import ReportAnswerForm, ReportForm

router = Router(name="user_menu")

_SUPER_ROLES = (UserRole.SUPERADMIN, UserRole.OWNER)
_PRIVATE = F.chat.type == ChatType.PRIVATE

# Кнопка подменю «Информация» -> слот контента.
_INFO_SLOTS = {
    texts.BTN.INFO_GUIDE: "guide",
    texts.BTN.INFO_RULES: "rules",
    texts.BTN.INFO_DOCS: "docs",
    texts.BTN.INFO_UPDATES: "updates",
    texts.BTN.INFO_BECOME_ORG: "become_organizer",
    texts.BTN.INFO_BECOME_ADMIN: "become_admin",
}


def _is_super(db_user: User | None) -> bool:
    return db_user is not None and db_user.current_role in _SUPER_ROLES


# --- Информация ---


@router.message(_PRIVATE, StateFilter(None), F.text == texts.BTN.INFO)
async def info_menu(message: Message, db_user: User | None) -> None:
    if db_user is None:
        return
    await message.answer(texts.INFO_PICK, reply_markup=info_menu_kb(_is_super(db_user)))


@router.message(_PRIVATE, StateFilter(None), F.text.in_(set(_INFO_SLOTS)))
async def info_show(message: Message, session: AsyncSession, db_user: User | None) -> None:
    if db_user is None:
        return
    content = await content_service.get_content(session, _INFO_SLOTS[message.text])
    await content_service.send_content(message, content)


@router.message(_PRIVATE, StateFilter(None), F.text == texts.BTN.INFO_ADMIN_REGS)
async def info_admin_regs(message: Message, session: AsyncSession, db_user: User | None) -> None:
    if db_user is None:
        return
    if not _is_super(db_user):
        await message.answer(texts.INFO_NO_ACCESS)
        return
    content = await content_service.get_content(session, "admin_regulations")
    await content_service.send_content(message, content)


@router.message(_PRIVATE, StateFilter(None), F.text == texts.BTN.BACK_TO_MENU)
async def back_to_menu(message: Message, db_user: User | None) -> None:
    await message.answer(texts.BACK_TO_MENU_DONE, reply_markup=main_menu_kb(db_user))


# --- Репорт кнопкой ---


@router.message(_PRIVATE, StateFilter(None), F.text == texts.BTN.REPORT)
async def report_start(message: Message, state: FSMContext, db_user: User | None) -> None:
    if db_user is None:
        await message.answer(texts.REPORT_NOT_REGISTERED)
        return
    await state.set_state(ReportForm.text)
    await message.answer(
        texts.REPORT_PROMPT.format(min=limits.REPORT_MIN, max=limits.REPORT_MAX),
        reply_markup=form_cancel_kb(),
    )


@router.message(ReportForm.text, F.text == texts.BTN.REG_CANCEL)
async def report_cancel(message: Message, state: FSMContext, db_user: User | None) -> None:
    await state.clear()
    await message.answer(texts.BACK_TO_MENU_DONE, reply_markup=main_menu_kb(db_user))


@router.message(ReportForm.text, CommandStart())
async def report_start_over(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User | None
) -> None:
    await state.clear()
    await send_start_screen(message, session, db_user)


@router.message(ReportForm.text, F.text, ~F.text.startswith("/"))
async def report_text(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User | None
) -> None:
    if db_user is None:
        await state.clear()
        return
    text = message.text.strip()
    if not limits.REPORT_MIN <= len(text) <= limits.REPORT_MAX:
        await message.answer(
            texts.REPORT_INVALID.format(min=limits.REPORT_MIN, max=limits.REPORT_MAX)
        )
        return
    await state.clear()
    report = await report_service.open_report(session, message.bot, db_user, text)
    await scenario_service.reply(
        message, session, "report_sent", main_menu_kb(db_user), number=report.report_id
    )


@router.message(ReportForm.text)
async def report_unexpected(message: Message) -> None:
    """Репорт: ответ на всё, что шагом не принимается.

    Скриншот к репорту приложить хочется в первую очередь, поэтому молчание
    здесь встречали чаще всего. Пока шаг принимает только текст — бот прямо
    говорит об этом и повторяет вопрос.
    """
    await message.answer(input_guard.form_explain(message))
    await message.answer(
        texts.REPORT_PROMPT.format(min=limits.REPORT_MIN, max=limits.REPORT_MAX),
        reply_markup=form_cancel_kb(),
    )


# --- Ответ автора репорта админам ---
#
# Разговор нужен обеим сторонам: админ спрашивает «а на каком экране это было?»,
# и без ответной кнопки человеку пришлось бы заводить второй репорт, потеряв
# связь с первым.


@router.callback_query(ReportAnswerCB.filter())
async def cb_report_answer(
    callback: CallbackQuery,
    callback_data: ReportAnswerCB,
    session: AsyncSession,
    state: FSMContext,
    db_user: User | None,
) -> None:
    report = await report_repo.get(session, callback_data.report_id)
    # Кнопка живёт в переписке долго, а репорт за это время могли закрыть.
    if report is None or db_user is None or report.author_tg_id != db_user.tg_id:
        await callback.answer(texts.REPORT_GONE, show_alert=True)
        return
    if report.status in CLOSED_REPORT_STATUSES:
        await callback.answer(texts.REPORT_ANSWER_CLOSED, show_alert=True)
        return
    await state.set_state(ReportAnswerForm.text)
    await state.update_data(report_id=report.report_id)
    await callback.message.answer(
        texts.REPORT_ANSWER_PROMPT.format(
            number=report.report_id,
            min=limits.REPORT_REPLY_MIN,
            max=limits.REPORT_REPLY_MAX,
        ),
        reply_markup=form_cancel_kb(),
    )
    await callback.answer()


@router.message(ReportAnswerForm.text, F.text == texts.BTN.REG_CANCEL)
async def report_answer_cancel(
    message: Message, state: FSMContext, db_user: User | None
) -> None:
    await state.clear()
    await message.answer(texts.BACK_TO_MENU_DONE, reply_markup=main_menu_kb(db_user))


@router.message(ReportAnswerForm.text, CommandStart())
async def report_answer_start_over(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User | None
) -> None:
    await state.clear()
    await send_start_screen(message, session, db_user)


@router.message(ReportAnswerForm.text, F.text, ~F.text.startswith("/"))
async def report_answer_text(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User | None
) -> None:
    if db_user is None:
        await state.clear()
        return
    text = message.text.strip()
    if not limits.REPORT_REPLY_MIN <= len(text) <= limits.REPORT_REPLY_MAX:
        await message.answer(
            texts.REPORT_REPLY_INVALID.format(
                min=limits.REPORT_REPLY_MIN, max=limits.REPORT_REPLY_MAX
            )
        )
        return
    data = await state.get_data()
    report = await report_repo.get(session, data.get("report_id"))
    await state.clear()
    if report is None:
        await message.answer(texts.REPORT_GONE, reply_markup=main_menu_kb(db_user))
        return
    await report_service.answer_from_author(session, message.bot, report, db_user, text)
    await message.answer(texts.REPORT_ANSWER_SENT, reply_markup=main_menu_kb(db_user))


@router.message(ReportAnswerForm.text)
async def report_answer_unexpected(message: Message, state: FSMContext) -> None:
    await message.answer(input_guard.form_explain(message))
    data = await state.get_data()
    await message.answer(
        texts.REPORT_ANSWER_PROMPT.format(
            number=data.get("report_id"),
            min=limits.REPORT_REPLY_MIN,
            max=limits.REPORT_REPLY_MAX,
        ),
        reply_markup=form_cancel_kb(),
    )


# --- Режим «Админство» (только меню, команды работают всегда) ---


@router.message(_PRIVATE, StateFilter(None), F.text == texts.BTN.ADMIN_MODE)
async def admin_mode_on(
    message: Message, session: AsyncSession, db_user: User | None
) -> None:
    if db_user is None or not has_admin_powers(db_user):
        return
    modules = await permission_service.effective_modules(session, db_user)
    await message.answer(texts.ADMIN_MODE_ON, reply_markup=admin_panel_kb(db_user, modules))


@router.message(_PRIVATE, StateFilter(None), F.text == texts.BTN.ADMIN_PANEL_USER_MODE)
async def admin_mode_off(message: Message, db_user: User | None) -> None:
    await message.answer(texts.ADMIN_MODE_OFF, reply_markup=main_menu_kb(db_user))


# «Пользователи» — routers/superadmin.py; «CRUD» — admin/crud_admin.py;
# «Сценарии» — admin/scenario_admin.py; «Логи» и «Обновления» — admin/owner_panel.py.
