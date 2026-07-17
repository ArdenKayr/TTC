"""Порядок в админ-чате.

- Служебный мусор (кто вошёл, кто вышел, смена названия и т.п.) удаляется,
  чтобы в теме заявок оставались только карточки и решения. Боту нужно право
  «Удаление сообщений» в админ-чате.
- Кнопка «Возьмусь» под вызовом админов: первый нажавший закрепляется в тексте
  сообщения, кнопка исчезает — остальные видят, что вызов уже разобран.
"""

from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.config import settings
from bot.db.models import User
from bot.keyboards.callback_data import AdminCallCB

router = Router(name="admin_chat")

# Общий фильтр «служебное сообщение» — им же пользуется чистка в общей группе.
SERVICE_MESSAGE = (
    F.new_chat_members
    | F.left_chat_member
    | F.new_chat_title
    | F.new_chat_photo
    | F.delete_chat_photo
    | F.pinned_message
    | F.message_auto_delete_timer_changed
)


@router.message(F.chat.id == settings.admin_chat_id, SERVICE_MESSAGE)
async def delete_service_message(message: Message) -> None:
    try:
        await message.delete()
    except TelegramAPIError:
        pass  # нет права «Удаление сообщений» — просто оставляем


@router.callback_query(AdminCallCB.filter())
async def cb_admin_call_claim(callback: CallbackQuery, db_user: User | None) -> None:
    message = callback.message
    if message is None or message.chat.id != settings.admin_chat_id:
        await callback.answer()
        return
    current_text = message.text or ""
    if texts.ADMIN_CALL_CLAIMED_MARK in current_text:
        await callback.answer(texts.ADMIN_CALL_ALREADY_TAKEN, show_alert=True)
        return
    name = db_user.display_name if db_user else callback.from_user.full_name
    try:
        await message.edit_text(
            escape(current_text) + texts.ADMIN_CALL_CLAIMED.format(name=escape(name)),
            reply_markup=None,
        )
    except TelegramAPIError:
        pass  # два одновременных нажатия: текст уже изменён первым
    await callback.answer(texts.ADMIN_CALL_CLAIM_OK)
