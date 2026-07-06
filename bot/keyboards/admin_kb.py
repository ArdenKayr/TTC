import uuid

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.keyboards.callback_data import RegReviewCB


def registration_review_kb(request_id: uuid.UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Принять",
                    callback_data=RegReviewCB(action="approve", request_id=str(request_id)).pack(),
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=RegReviewCB(action="reject", request_id=str(request_id)).pack(),
                ),
            ]
        ]
    )
