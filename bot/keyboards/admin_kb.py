import uuid

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import texts
from bot.keyboards.callback_data import ContentActionCB, ContentSlotCB, RegReviewCB


def content_slots_kb(slots) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=slot.title, callback_data=ContentSlotCB(slot=slot.key).pack())]
        for slot in slots
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def content_edit_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BTN.CONTENT_REMOVE_FILE,
                    callback_data=ContentActionCB(action="remove_file").pack(),
                ),
                InlineKeyboardButton(
                    text=texts.BTN.CONTENT_CANCEL,
                    callback_data=ContentActionCB(action="cancel").pack(),
                ),
            ]
        ]
    )


def registration_review_kb(request_id: uuid.UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BTN.REVIEW_APPROVE,
                    callback_data=RegReviewCB(action="approve", request_id=str(request_id)).pack(),
                ),
                InlineKeyboardButton(
                    text=texts.BTN.REVIEW_REJECT,
                    callback_data=RegReviewCB(action="reject", request_id=str(request_id)).pack(),
                ),
            ]
        ]
    )
