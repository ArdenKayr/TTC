"""Очередь разбора заявок («🛠 Админство» → «📥 Заявки»).

Раздел открыт каждому, кто хоть что-то разбирает: и тому, у кого включён
только модуль регистраций, и тому, кто занят одними вузами. Внутри каждый
видит свои виды заявок — и никаких чужих.

Сам разбор здесь не живёт. Кнопки под карточками те же, что и в админ-чате,
и нажатия по ним ловят те же обработчики в соседних файлах: очередь только
достаёт заявку из базы и показывает её заново.
"""

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.db.models import User
from bot.enums import PermissionModule
from bot.filters.role_filter import HasAnyPerm
from bot.keyboards.admin_kb import queue_kb
from bot.keyboards.callback_data import QueueCB
from bot.routers.admin import review_ui
from bot.services import permission_service, queue_service

router = Router(name="admin_queue")

_PRIVATE = F.chat.type == ChatType.PRIVATE

# Модули, любой из которых открывает раздел. Держим списком, а не «любым
# админством»: человек с одними только репортами разбирать заявки не должен.
_QUEUE_MODULES = (
    PermissionModule.REGISTRATION,
    PermissionModule.ACTIVITIES,
    PermissionModule.UNIVERSITIES,
)


@router.message(
    _PRIVATE,
    StateFilter(None),
    F.text == texts.BTN.ADMIN_PANEL_QUEUE,
    HasAnyPerm(*_QUEUE_MODULES),
)
async def btn_queue(message: Message, session: AsyncSession, db_user: User) -> None:
    """Сводка очереди: сколько заявок какого вида ждут решения."""
    modules = await permission_service.effective_modules(session, db_user)
    totals = await queue_service.counts(session, modules)
    if not any(totals.values()):
        await message.answer(texts.QUEUE_EMPTY)
        return
    waiting = [
        (kind.key, kind.title)
        for kind in queue_service.allowed(modules)
        if totals.get(kind.key)
    ]
    await message.answer(queue_service.render_summary(totals), reply_markup=queue_kb(waiting))


@router.callback_query(QueueCB.filter(), HasAnyPerm(*_QUEUE_MODULES))
async def cb_queue_kind(
    callback: CallbackQuery, callback_data: QueueCB, session: AsyncSession, db_user: User
) -> None:
    """Присылает свежие карточки самых давних заявок выбранного вида."""
    kind = queue_service.BY_KEY.get(callback_data.kind)
    if kind is None or not await permission_service.has_permission(
        session, db_user, kind.module
    ):
        await callback.answer(texts.QUEUE_NO_ACCESS, show_alert=True)
        return
    total = await queue_service.count(session, kind.key)
    if total == 0:
        # Пока сводка висела в чате, заявки успели разобрать — это норма.
        await callback.answer(texts.QUEUE_KIND_EMPTY, show_alert=True)
        return

    # Дальше идёт долгая работа — десяток сообщений в личку, — а на ответ по
    # нажатию Telegram отводит секунды. Подтверждаем сейчас.
    await review_ui.ack(callback)
    batch = await queue_service.cards(session, kind.key)
    shown = await queue_service.send(callback.bot, callback.from_user.id, batch)
    footer = (
        texts.QUEUE_ALL_SHOWN.format(total=total)
        if shown >= total
        else texts.QUEUE_SHOWN.format(shown=shown, total=total)
    )
    await callback.bot.send_message(callback.from_user.id, footer)


@router.callback_query(QueueCB.filter())
async def cb_no_permission(callback: CallbackQuery) -> None:
    await callback.answer(texts.REVIEW_ADMIN_ONLY, show_alert=True)
