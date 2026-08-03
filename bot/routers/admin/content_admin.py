from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.db.models import User
from bot.enums import PermissionModule
from bot.filters.role_filter import HasPerm
from bot.keyboards.admin_kb import content_edit_kb, content_slots_kb
from bot.keyboards.callback_data import ContentActionCB, ContentSlotCB
from bot.services import content_service, input_guard
from bot.states.content_states import ContentEditForm

router = Router(name="admin_content")
router.message.filter(HasPerm(PermissionModule.CONTENT))
router.callback_query.filter(HasPerm(PermissionModule.CONTENT))


@router.message(
    F.chat.type == ChatType.PRIVATE,
    StateFilter(None),
    F.text == texts.BTN.ADMIN_PANEL_CONTENT,
)
async def btn_content(message: Message, state: FSMContext) -> None:
    """Список страниц бота: «🛠 Админство» → «📄 Разделы».

    Раньше сюда вела команда /content, которой не было ни в одном меню, —
    редактор страниц выглядел так, будто его вовсе нет.
    """
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


async def _saved(message: Message, session: AsyncSession, slot_key: str) -> None:
    """«Сохранено» + как блок теперь выглядит (оформление видно сразу)."""
    await message.answer(texts.CONTENT_SAVED)
    content = await content_service.get_content(session, slot_key)
    try:
        await content_service.send_content(message, content)
    except Exception:
        await message.answer(texts.CONTENT_SAVED_BAD_HTML)


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
        caption=content_service.formatted_text(message) or None,
    )
    await state.clear()
    await _saved(message, session, data["slot"])


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
        caption=content_service.formatted_text(message) or None,
    )
    await state.clear()
    await _saved(message, session, data["slot"])


@router.message(ContentEditForm.waiting, F.text)
async def msg_new_text(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    data = await state.get_data()
    await content_service.update_text(
        session, db_user, data["slot"], content_service.formatted_text(message)
    )
    await state.clear()
    await _saved(message, session, data["slot"])


@router.message(ContentEditForm.waiting)
async def msg_unexpected(message: Message, state: FSMContext) -> None:
    """Ответ на то, что редактор принять не может: стикер, голосовое, кружок.

    Стоит последним в роутере: текст, фото и файл разбирают обработчики выше.
    """
    data = await state.get_data()
    slot = content_service.SLOTS.get(data.get("slot"))
    await message.answer(input_guard.form_explain(message, files_ok=True))
    if slot is not None:
        await message.answer(
            texts.CONTENT_PROMPT.format(title=slot.title), reply_markup=content_edit_kb()
        )
