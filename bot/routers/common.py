from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.db.models import User
from bot.keyboards.callback_data import StartCB
from bot.keyboards.common_kb import main_menu_kb
from bot.services import content_service, notification_service

router = Router(name="common")


@router.message(CommandStart(), F.chat.type == ChatType.PRIVATE)
async def cmd_start(message: Message, session: AsyncSession, db_user: User | None) -> None:
    if db_user is None:
        content = await content_service.get_content(session, "welcome")
        await content_service.send_content(
            message, content, keyboard=main_menu_kb(registered=False)
        )
        return
    role = texts.ROLE_LABELS.get(db_user.current_role, db_user.current_role.value)
    await message.answer(
        texts.START_REGISTERED.format(name=db_user.display_name, role=role),
        reply_markup=main_menu_kb(registered=True),
    )


@router.message(F.chat.type == ChatType.PRIVATE, F.text == texts.BTN.START_ABOUT)
async def msg_about(message: Message, session: AsyncSession) -> None:
    """Кнопка «Кто мы?» в меню (меню остаётся на месте)."""
    content = await content_service.get_content(session, "about")
    await content_service.send_content(message, content)


@router.callback_query(StartCB.filter(F.action == "about"))
async def cb_about(callback: CallbackQuery, session: AsyncSession) -> None:
    """Кнопка «Кто мы?» под старыми приветственными сообщениями."""
    content = await content_service.get_content(session, "about")
    await content_service.send_content(callback.message, content)
    await callback.answer()


@router.message(Command("report"), F.chat.type == ChatType.PRIVATE)
async def cmd_report(message: Message, command: CommandObject, db_user: User | None) -> None:
    if db_user is None:
        await message.answer(texts.REPORT_NOT_REGISTERED)
        return
    text = (command.args or "").strip()
    if not text:
        await message.answer(texts.REPORT_USAGE)
        return
    username = f"@{db_user.username}" if db_user.username else f"id {db_user.tg_id}"
    await notification_service.send_admin_report(
        message.bot,
        texts.REPORT_CARD.format(name=db_user.display_name, username=username, text=text),
    )
    await message.answer(texts.REPORT_SENT)
