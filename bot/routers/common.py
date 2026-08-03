
from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.db.models import User
from bot.keyboards.callback_data import StartCB
from bot.keyboards.common_kb import main_menu_kb
from bot.routers.group.admin_chat import SERVICE_MESSAGE
from bot.services import content_service, input_guard

router = Router(name="common")


async def send_start_screen(
    message: Message, session: AsyncSession, db_user: User | None
) -> None:
    """Главный экран: приветствие/статус + постоянное меню внизу.

    Используется и командой /start здесь, и «спасательным» /start внутри анкеты.
    """
    if db_user is None:
        content = await content_service.get_content(session, "welcome")
        await content_service.send_content(message, content, keyboard=main_menu_kb(None))
        return
    role = texts.ROLE_LABELS.get(db_user.current_role, db_user.current_role.value)
    await message.answer(
        texts.START_REGISTERED.format(name=db_user.display_name, role=role),
        reply_markup=main_menu_kb(db_user),
    )


@router.message(CommandStart(), F.chat.type == ChatType.PRIVATE)
async def cmd_start(message: Message, session: AsyncSession, db_user: User | None) -> None:
    await send_start_screen(message, session, db_user)


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


# --- Последний рубеж всего бота ---


@router.message(F.chat.type == ChatType.PRIVATE, ~SERVICE_MESSAGE)
async def unknown_input(message: Message, db_user: User | None) -> None:
    """Ответ на всё, что не разобрал никто выше: «привет», стикер, старая команда.

    Роутер подключается последним, а этот обработчик — последний в нём, поэтому
    сюда попадает только то, что не взял ни один обработчик бота. Раньше здесь
    было молчание, и человек не мог отличить «бот меня не понял» от «бот упал».
    Заодно возвращаем меню: обычно оно и потерялось.

    Только личка: в группах бот отвечает не на всё подряд — там свой сторож.
    """
    await message.answer(
        input_guard.menu_explain(message), reply_markup=main_menu_kb(db_user)
    )


