"""Разбор репортов (модуль прав «Репорты»).

- Кнопки под карточкой в админ-чате: ответить автору, взять в работу, закрыть.
- «🛠 Админство» → «🐞 Репорты» — очередь незакрытых. Карточка в чате уезжает
  вверх за час, а репорт живёт неделями: без списка он терялся бы ровно так же,
  как раньше терялось само сообщение.
"""

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from bot import limits, texts
from bot.db.models import User
from bot.db.repositories import report_repo
from bot.enums import PermissionModule, ReportStatus
from bot.filters.role_filter import HasPerm
from bot.keyboards.callback_data import ReportCB, ReportReplyCB
from bot.keyboards.common_kb import MENU_BUTTON_TEXTS, admin_panel_kb
from bot.keyboards.report_kb import report_card_kb, report_reply_cancel_kb
from bot.services import (
    input_guard,
    permission_service,
    report_service,
    scenario_service,
)
from bot.states.profile_states import ReportReplyForm

router = Router(name="admin_report_review")

_PRIVATE = F.chat.type == ChatType.PRIVATE

# Кнопка решения -> статус, который она ставит.
_ACTION_STATUS = {
    "progress": ReportStatus.IN_PROGRESS,
    "done": ReportStatus.DONE,
    "decline": ReportStatus.DECLINED,
}

# Чем закончилась отправка автору — это админ и увидит в ответе. Строки разные
# для ответа и для смены статуса: «ответ не дошёл» про нажатие «✅ Готово»
# сбивало бы с толку.
_REPLY_NOTE = {
    scenario_service.Delivery.SENT: texts.REPORT_REPLY_SENT,
    scenario_service.Delivery.FAILED: texts.REPORT_REPLY_FAILED,
    scenario_service.Delivery.NO_ADDRESSEE: texts.REPORT_REPLY_NO_ADDRESSEE,
}
_STATUS_NOTE = {
    scenario_service.Delivery.SENT: texts.REPORT_STATUS_SAVED,
    scenario_service.Delivery.FAILED: texts.REPORT_NOTICE_FAILED,
    scenario_service.Delivery.NO_ADDRESSEE: texts.REPORT_NOTICE_NO_ADDRESSEE,
}


async def _panel(session: AsyncSession, db_user: User) -> ReplyKeyboardMarkup:
    modules = await permission_service.effective_modules(session, db_user)
    return admin_panel_kb(db_user, modules)


# --- Кнопки под карточкой ---


@router.callback_query(ReportCB.filter(F.action == "reply"), HasPerm(PermissionModule.REPORTS))
async def cb_report_reply(
    callback: CallbackQuery, callback_data: ReportCB, session: AsyncSession, state: FSMContext
) -> None:
    report = await report_repo.get(session, callback_data.report_id)
    if report is None:
        await callback.answer(texts.REPORT_GONE, show_alert=True)
        return
    await state.set_state(ReportReplyForm.text)
    await state.update_data(report_id=report.report_id)
    await callback.message.answer(
        texts.REPORT_REPLY_PROMPT.format(
            number=report.report_id,
            min=limits.REPORT_REPLY_MIN,
            max=limits.REPORT_REPLY_MAX,
        ),
        reply_markup=report_reply_cancel_kb(),
    )
    await callback.answer()


@router.callback_query(
    ReportCB.filter(F.action.in_(tuple(_ACTION_STATUS))), HasPerm(PermissionModule.REPORTS)
)
async def cb_report_status(
    callback: CallbackQuery, callback_data: ReportCB, session: AsyncSession, db_user: User
) -> None:
    report = await report_repo.get(session, callback_data.report_id)
    if report is None:
        await callback.answer(texts.REPORT_GONE, show_alert=True)
        return
    status = _ACTION_STATUS[callback_data.action]
    if report.status is status:
        await callback.answer(texts.REPORT_SAME_STATUS, show_alert=True)
        return
    delivery = await report_service.change_status(session, callback.bot, report, db_user, status)
    # Автору не дошло — админ должен знать: иначе он уверен, что человек
    # предупреждён, а тот сидит без ответа. Поэтому неудача показывается
    # заметным окном, а успех — обычной всплывашкой.
    await callback.answer(_STATUS_NOTE[delivery], show_alert=not delivery)


@router.callback_query(ReportReplyCB.filter(), HasPerm(PermissionModule.REPORTS))
async def cb_report_reply_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(texts.REPORT_REPLY_CANCELLED, reply_markup=None)
    await callback.answer()


# --- Ответ админа автору ---


@router.message(
    StateFilter(ReportReplyForm),
    F.text.in_(MENU_BUTTON_TEXTS),
    HasPerm(PermissionModule.REPORTS),
)
async def reply_menu_pressed(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    """Кнопка меню посреди ответа — это выход, а не текст ответа."""
    await state.clear()
    await message.answer(texts.ADMIN_MODE_ON, reply_markup=await _panel(session, db_user))


@router.message(
    ReportReplyForm.text, F.text, ~F.text.startswith("/"), HasPerm(PermissionModule.REPORTS)
)
async def reply_text(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
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
        await message.answer(texts.REPORT_GONE)
        return
    delivery = await report_service.reply_to_author(
        session, message.bot, report, db_user, text
    )
    await message.answer(_REPLY_NOTE[delivery])


@router.message(StateFilter(ReportReplyForm), HasPerm(PermissionModule.REPORTS))
async def reply_unexpected(message: Message, state: FSMContext) -> None:
    """Ответ на всё, что шагом не принимается: молчать в ответ бот не должен."""
    await message.answer(input_guard.form_explain(message))
    data = await state.get_data()
    await message.answer(
        texts.REPORT_REPLY_PROMPT.format(
            number=data.get("report_id"),
            min=limits.REPORT_REPLY_MIN,
            max=limits.REPORT_REPLY_MAX,
        ),
        reply_markup=report_reply_cancel_kb(),
    )


# --- Очередь репортов в панели ---


@router.message(
    _PRIVATE,
    StateFilter(None),
    F.text == texts.BTN.ADMIN_PANEL_REPORTS,
    HasPerm(PermissionModule.REPORTS),
)
async def btn_reports(message: Message, session: AsyncSession) -> None:
    reports = await report_repo.list_open(session)
    if not reports:
        await message.answer(texts.REPORT_LIST_EMPTY)
        return
    for report in reports:
        await message.answer(
            await report_service.render_card(session, report),
            reply_markup=report_card_kb(report),
        )


@router.callback_query(ReportCB.filter())
@router.callback_query(ReportReplyCB.filter())
async def cb_no_permission(callback: CallbackQuery) -> None:
    await callback.answer(texts.REVIEW_ADMIN_ONLY, show_alert=True)
