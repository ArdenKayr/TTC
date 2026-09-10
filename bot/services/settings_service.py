"""Переключатели, которые владелец меняет из панели, а не выкаткой.

Настройки бота живут в двух местах, и это разделение намеренное. В `.env` —
то, что описывает саму установку: токен, номера чатов, адрес базы. Меняется
редко, требует доступа к серверу и перезапуска — и правильно, что требует.

Здесь — то, что владелец решает по ходу жизни сообщества: включить автоприём
перед наплывом, выключить, когда наплыв кончился. Такой рычаг должен быть под
рукой в любую минуту, в том числе с телефона.

Каждое переключение пишется в журнал действий: «кто, когда, что включил» —
вопрос «почему этого человека впустили без нас» должен иметь ответ.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import BotSetting, User
from bot.db.repositories import audit_repo
from bot.enums import AuditAction

# Пускать ли подходящие заявки на вступление без админа.
AUTO_APPROVE = "auto_approve"

_ON = "on"
_OFF = "off"


async def is_on(session: AsyncSession, key: str) -> bool:
    """Включён ли переключатель. Нет записи — значит выключен.

    Отсутствие записи и «выключено» — одно и то же намеренно: обновление,
    добавившее переключатель, не должно ничего включать само.
    """
    value = await session.scalar(select(BotSetting.value).where(BotSetting.key == key))
    return value == _ON


async def toggle(session: AsyncSession, key: str, owner: User) -> bool:
    """Переключает и возвращает новое состояние (включено?)."""
    row = await session.get(BotSetting, key)
    new_state = not (row is not None and row.value == _ON)
    if row is None:
        session.add(BotSetting(key=key, value=_ON if new_state else _OFF, updated_by=owner.tg_id))
    else:
        row.value = _ON if new_state else _OFF
        row.updated_by = owner.tg_id
    await audit_repo.add(
        session,
        AuditAction.SETTING_CHANGED,
        actor_tg_id=owner.tg_id,
        target_entity_type="bot_setting",
        target_entity_id=key,
        meta={"value": _ON if new_state else _OFF},
    )
    await session.commit()
    return new_state
