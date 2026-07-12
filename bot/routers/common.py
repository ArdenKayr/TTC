from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

from bot import texts
from bot.db.models import User
from bot.services import notification_service

router = Router(name="common")


@router.message(CommandStart(), F.chat.type == ChatType.PRIVATE)
async def cmd_start(message: Message, db_user: User | None) -> None:
    if db_user is None:
        await message.answer(texts.START_NEW_USER)
        return
    role = texts.ROLE_LABELS.get(db_user.current_role, db_user.current_role.value)
    await message.answer(texts.START_REGISTERED.format(name=db_user.display_name, role=role))


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
