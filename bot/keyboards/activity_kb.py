from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from bot import texts
from bot.keyboards.callback_data import ActLifecycleCB, ActReviewCB, VoteReviewCB

_CANCEL_ROW = [KeyboardButton(text=texts.BTN.REG_CANCEL)]


def _reply(rows: list[list[KeyboardButton]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def form_cancel_kb() -> ReplyKeyboardMarkup:
    """Обычный шаг заявки: только «Отмена»."""
    return _reply([_CANCEL_ROW])


def url_step_kb() -> ReplyKeyboardMarkup:
    """Шаг ссылки: можно пропустить."""
    return _reply([[KeyboardButton(text=texts.BTN.ACT_SKIP_URL)], _CANCEL_ROW])


def confirm_kb() -> ReplyKeyboardMarkup:
    """Подтверждение заявки (те же кнопки, что в анкете регистрации)."""
    return _reply(
        [
            [KeyboardButton(text=texts.BTN.REG_SUBMIT)],
            [KeyboardButton(text=texts.BTN.REG_RESTART), KeyboardButton(text=texts.BTN.REG_CANCEL)],
        ]
    )


def act_review_kb(request_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BTN.REVIEW_APPROVE,
                    callback_data=ActReviewCB(action="approve", request_id=request_id).pack(),
                ),
                InlineKeyboardButton(
                    text=texts.BTN.REVIEW_REJECT,
                    callback_data=ActReviewCB(action="reject", request_id=request_id).pack(),
                ),
            ]
        ]
    )


def vote_review_kb(request_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BTN.REVIEW_APPROVE,
                    callback_data=VoteReviewCB(action="approve", request_id=request_id).pack(),
                ),
                InlineKeyboardButton(
                    text=texts.BTN.REVIEW_REJECT,
                    callback_data=VoteReviewCB(action="reject", request_id=request_id).pack(),
                ),
            ]
        ]
    )


def act_lifecycle_kb(activity_id: str) -> InlineKeyboardMarkup:
    """Кнопки под карточкой активного мероприятия в списке /activities."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BTN.ACT_COMPLETE,
                    callback_data=ActLifecycleCB(action="complete", activity_id=activity_id).pack(),
                ),
                InlineKeyboardButton(
                    text=texts.BTN.ACT_CANCEL_ACT,
                    callback_data=ActLifecycleCB(action="cancel", activity_id=activity_id).pack(),
                ),
            ]
        ]
    )
