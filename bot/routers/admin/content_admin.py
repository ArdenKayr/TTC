from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.db.models import User
from bot.filters.role_filter import IsAdmin
from bot.keyboards.admin_kb import content_edit_kb, content_slots_kb
from bot.keyboards.callback_data import ContentActionCB, ContentSlotCB
from bot.services import content_service
from bot.states.content_states import ContentEditForm

router = Router(name="admin_content")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


@router.message(Command("content"), F.chat.type == ChatType.PRIVATE)
async def cmd_content(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        texts.CONTENT_PICK, reply_markup=content_slots_kb(content_service.SLOTS.values())
    )


@router.callback_query(ContentSlotCB.filter())
async def cb_pick_slot(
    callback: CallbackQuery,
    callback_data: ContentSlotCB,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    slot = content_service.SLOTS.get(callback_data.slot)
    if slot is None:
        await callback.answer(texts.CONTENT_UNKNOWN_SLOT, show_alert=True)
        return
    content = await content_service.get_content(session, slot.key)
    await callback.message.answer(texts.CONTENT_CURRENT.format(title=slot.title))
    await content_service.send_content(callback.message, content)
    await state.set_state(ContentEditForm.waiting)
    await state.update_data(slot=slot.key)
    await callback.message.answer(
        texts.CONTENT_PROMPT.format(title=slot.title), reply_markup=content_edit_kb()
    )
    await callback.answer()


@router.callback_query(ContentActionCB.filter(F.action == "cancel"))
async def cb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(texts.CONTENT_CANCELLED)
    await callback.answer()


@router.callback_query(ContentActionCB.filter(F.action == "remove_file"), ContentEditForm.waiting)
async def cb_remove_file(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    data = await state.get_data()
    await content_service.remove_file(session, db_user, data["slot"])
    await state.clear()
    await callback.message.edit_text(texts.CONTENT_FILE_REMOVED)
    await callback.answer()


@router.message(ContentEditForm.waiting, F.photo)
async def msg_new_photo(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    data = await state.get_data()
    await content_service.update_file(
        session,
        db_user,
        data["slot"],
        file_id=message.photo[-1].file_id,
        file_type="photo",
        caption=(message.caption or "").strip() or None,
    )
    await state.clear()
    await message.answer(texts.CONTENT_SAVED)


@router.message(ContentEditForm.waiting, F.document)
async def msg_new_document(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    data = await state.get_data()
    await content_service.update_file(
        session,
        db_user,
        data["slot"],
        file_id=message.document.file_id,
        file_type="document",
        caption=(message.caption or "").strip() or None,
    )
    await state.clear()
    await message.answer(texts.CONTENT_SAVED)


@router.message(ContentEditForm.waiting, F.text)
async def msg_new_text(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    data = await state.get_data()
    await content_service.update_text(session, db_user, data["slot"], message.text.strip())
    await state.clear()
    await message.answer(texts.CONTENT_SAVED)
