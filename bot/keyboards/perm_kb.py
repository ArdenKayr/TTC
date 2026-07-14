from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import texts
from bot.db.models import PermissionGroup, User
from bot.keyboards.callback_data import (
    GroupDeleteCB,
    GroupMembersCB,
    GroupOpenCB,
    GroupToggleCB,
    PermCancelCB,
    PermHomeCB,
    PermNewGroupCB,
    PermPersonCB,
    UserGroupSetCB,
    UserModToggleCB,
)
from bot.services.permission_service import MODULES


def _check(enabled: bool) -> str:
    return "✅" if enabled else "⬜"


def perm_home_kb(groups: list[PermissionGroup]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=texts.PERM_GROUP_ROW.format(
                    name=group.name, count=len(group.modules or [])
                ),
                callback_data=GroupOpenCB(group_id=group.group_id).pack(),
            )
        ]
        for group in groups
    ]
    rows.append(
        [InlineKeyboardButton(text=texts.BTN.PERM_NEW_GROUP, callback_data=PermNewGroupCB().pack())]
    )
    rows.append(
        [InlineKeyboardButton(text=texts.BTN.PERM_PERSON, callback_data=PermPersonCB().pack())]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def perm_group_kb(group: PermissionGroup) -> InlineKeyboardMarkup:
    enabled = set(group.modules or [])
    rows = [
        [
            InlineKeyboardButton(
                text=f"{_check(module.key in enabled)} {module.title}",
                callback_data=GroupToggleCB(group_id=group.group_id, module=module.key).pack(),
            )
        ]
        for module in MODULES.values()
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=texts.BTN.PERM_MEMBERS,
                callback_data=GroupMembersCB(group_id=group.group_id).pack(),
            ),
            InlineKeyboardButton(
                text=texts.BTN.PERM_DELETE,
                callback_data=GroupDeleteCB(group_id=group.group_id).pack(),
            ),
        ]
    )
    rows.append([InlineKeyboardButton(text=texts.BTN.PERM_BACK, callback_data=PermHomeCB().pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def perm_group_delete_kb(group_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BTN.PERM_DELETE_YES,
                    callback_data=GroupDeleteCB(group_id=group_id, confirmed=True).pack(),
                ),
                InlineKeyboardButton(
                    text=texts.BTN.PERM_BACK,
                    callback_data=GroupOpenCB(group_id=group_id).pack(),
                ),
            ]
        ]
    )


def perm_back_to_group_kb(group_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BTN.PERM_BACK,
                    callback_data=GroupOpenCB(group_id=group_id).pack(),
                )
            ]
        ]
    )


def perm_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.BTN.PERM_CANCEL, callback_data=PermCancelCB().pack())]
        ]
    )


def perm_person_kb(
    target: User, personal: set[str], groups: list[PermissionGroup]
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{_check(module.key in personal)} {module.title}",
                callback_data=UserModToggleCB(tg_id=target.tg_id, module=module.key).pack(),
            )
        ]
        for module in MODULES.values()
    ]
    for group in groups:
        mark = "📁✅" if target.permission_group_id == group.group_id else "📁"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark} {group.name}",
                    callback_data=UserGroupSetCB(
                        tg_id=target.tg_id, group_id=group.group_id
                    ).pack(),
                )
            ]
        )
    if target.permission_group_id is not None:
        rows.append(
            [
                InlineKeyboardButton(
                    text=texts.BTN.PERM_NO_GROUP,
                    callback_data=UserGroupSetCB(tg_id=target.tg_id, group_id=0).pack(),
                )
            ]
        )
    rows.append([InlineKeyboardButton(text=texts.BTN.PERM_BACK, callback_data=PermHomeCB().pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)
