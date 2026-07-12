import uuid

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import texts
from bot.keyboards.callback_data import (
    AliasSugCB,
    ContentActionCB,
    ContentSlotCB,
    RegReviewCB,
    ReviewEditCB,
    UniReqCB,
)


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


def university_request_review_kb(request_id: uuid.UUID) -> InlineKeyboardMarkup:
    rid = str(request_id)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BTN.REVIEW_APPROVE,
                    callback_data=UniReqCB(action="approve", request_id=rid).pack(),
                ),
                InlineKeyboardButton(
                    text=texts.BTN.REVIEW_REJECT,
                    callback_data=UniReqCB(action="reject", request_id=rid).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=texts.BTN.REVIEW_EDIT,
                    callback_data=UniReqCB(action="edit", request_id=rid).pack(),
                )
            ],
        ]
    )


def alias_suggestion_review_kb(suggestion_id: uuid.UUID) -> InlineKeyboardMarkup:
    sid = str(suggestion_id)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BTN.REVIEW_APPROVE,
                    callback_data=AliasSugCB(action="approve", suggestion_id=sid).pack(),
                ),
                InlineKeyboardButton(
                    text=texts.BTN.REVIEW_REJECT,
                    callback_data=AliasSugCB(action="reject", suggestion_id=sid).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=texts.BTN.REVIEW_EDIT,
                    callback_data=AliasSugCB(action="edit", suggestion_id=sid).pack(),
                )
            ],
        ]
    )


def review_edit_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BTN.EDIT_CANCEL,
                    callback_data=ReviewEditCB(action="cancel").pack(),
                )
            ]
        ]
    )
