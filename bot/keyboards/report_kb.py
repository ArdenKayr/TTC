from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import texts
from bot.db.models import Report
from bot.enums import CLOSED_REPORT_STATUSES, ReportStatus
from bot.keyboards.callback_data import ReportAnswerCB, ReportCB, ReportReplyCB


def report_card_kb(report: Report) -> InlineKeyboardMarkup:
    """Кнопки под карточкой репорта — только те, что сейчас имеют смысл.

    Закрытый репорт не предлагает закрыть его ещё раз, а взятый в работу — взять
    повторно. Зато вернуть закрытый в работу можно всегда: решение админа не
    приговор, а автор может написать что-то, что его меняет.
    """
    rid = report.report_id
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=texts.BTN.REPORT_REPLY,
                callback_data=ReportCB(action="reply", report_id=rid).pack(),
            )
        ]
    ]
    decisions: list[InlineKeyboardButton] = []
    if report.status is not ReportStatus.IN_PROGRESS:
        decisions.append(
            InlineKeyboardButton(
                text=texts.BTN.REPORT_PROGRESS,
                callback_data=ReportCB(action="progress", report_id=rid).pack(),
            )
        )
    if report.status not in CLOSED_REPORT_STATUSES:
        decisions.append(
            InlineKeyboardButton(
                text=texts.BTN.REPORT_DONE,
                callback_data=ReportCB(action="done", report_id=rid).pack(),
            )
        )
        decisions.append(
            InlineKeyboardButton(
                text=texts.BTN.REPORT_DECLINE,
                callback_data=ReportCB(action="decline", report_id=rid).pack(),
            )
        )
    if decisions:
        rows.append(decisions)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def report_reply_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BTN.REPORT_REPLY_CANCEL,
                    callback_data=ReportReplyCB().pack(),
                )
            ]
        ]
    )


def report_answer_kb(report_id: int) -> InlineKeyboardMarkup:
    """«Ответить» под сообщением автору — иначе разговор был бы односторонним."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BTN.REPORT_REPLY,
                    callback_data=ReportAnswerCB(report_id=report_id).pack(),
                )
            ]
        ]
    )
