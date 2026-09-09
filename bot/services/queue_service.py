"""Очередь неразобранных заявок: разобрать не сейчас, а когда дойдут руки.

Карточка заявки приходит в админ-чат один раз, и до сентября 2026 она была
единственным способом заявку разобрать. Это работало, пока заявок было
несколько в день, и разваливалось в двух случаях сразу.

**Отложить решение было нельзя.** Владелец 09.09.2026: «хочу принимать
мероприятие не сразу, а, допустим, на следующий день». К этому времени
карточка уезжает вверх чата, а Telegram перестаёт присылать её содержимое —
в нажатии кнопки вместо сообщения приходит заглушка без текста. Само решение
проходило, но выглядело сломанным (подробнее — в `routers/admin/review_ui`).

**Потерянная карточка означала потерянную заявку.** Отправка в чат может не
пройти — упёрлись в лимит (в одну группу Telegram пускает 20 сообщений в
минуту, а на наплыве регистраций это первое, во что бот упирается), чат
недоступен, права отобраны. Заявка при этом лежит в базе и ждёт, но увидеть
её было негде.

Очередь и решает обе беды: она смотрит не на сообщения в чате, а в базу, и
выдаёт свежую карточку со свежими кнопками в любой момент. Разобранная
заявка из очереди исчезает сама — статус у неё уже не «ждёт».

Разбирают отсюда те же самые кнопки, что и в админ-чате: обработчики решений
живут в `routers/admin/` и ничего не знают о том, откуда пришло нажатие.
"""

from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.db.models import (
    ActivityRequest,
    AliasSuggestion,
    RegistrationRequest,
    UniversityRequest,
    User,
    VoteRequest,
)
from bot.db.repositories import university_repo
from bot.enums import PermissionModule, RequestStatus
from bot.keyboards.activity_kb import act_review_kb, vote_review_kb
from bot.keyboards.admin_kb import (
    alias_suggestion_review_kb,
    registration_review_kb,
    university_request_review_kb,
)
from bot.services import (
    activity_service,
    notification_service,
    registration_service,
    university_service,
)

# Сколько карточек присылать за одно нажатие. Больше — вредно: каждая
# карточка это отдельное сообщение, а в одну личку Telegram пускает примерно
# по сообщению в секунду. Да и разбирать сотню подряд никто не станет.
PAGE = 10


@dataclass(frozen=True)
class Kind:
    """Вид заявок в очереди: своя кнопка, свой модуль прав, свой запрос."""

    key: str
    title: str
    module: PermissionModule


KINDS: tuple[Kind, ...] = (
    Kind("reg", texts.BTN.QUEUE_REG, PermissionModule.REGISTRATION),
    Kind("act", texts.BTN.QUEUE_ACT, PermissionModule.ACTIVITIES),
    Kind("vote", texts.BTN.QUEUE_VOTE, PermissionModule.ACTIVITIES),
    Kind("uni", texts.BTN.QUEUE_UNI, PermissionModule.UNIVERSITIES),
    Kind("alias", texts.BTN.QUEUE_ALIAS, PermissionModule.UNIVERSITIES),
)

BY_KEY: dict[str, Kind] = {kind.key: kind for kind in KINDS}


@dataclass(frozen=True)
class Card:
    """Готовая карточка: что показать и какие кнопки под ней."""

    text: str
    keyboard: InlineKeyboardMarkup
    photo_file_id: str | None = None


def _pending_registrations() -> Select:
    """Заявки на вступление, которые действительно ждут решения админа.

    Заявка, поданная вместе с заявкой на новый вуз, ждёт не админа, а решения
    по вузу: её карточка уходит в чат уже после него. Показать такую в
    очереди — значит позвать разбирать то, что ещё не готово, и одобрить
    человека с вузом, которого в справочнике нет.
    """
    return (
        select(RegistrationRequest)
        .outerjoin(
            UniversityRequest,
            RegistrationRequest.university_request_id == UniversityRequest.request_id,
        )
        .where(
            RegistrationRequest.status == RequestStatus.PENDING,
            or_(
                RegistrationRequest.university_request_id.is_(None),
                UniversityRequest.status != RequestStatus.PENDING,
            ),
        )
        .order_by(RegistrationRequest.created_at)
    )


def statement(kind_key: str) -> Select:
    """Запрос за неразобранными заявками одного вида, от самых давних."""
    if kind_key == "reg":
        return _pending_registrations()
    if kind_key == "act":
        return (
            select(ActivityRequest)
            .where(ActivityRequest.status == RequestStatus.PENDING)
            .order_by(ActivityRequest.created_at)
        )
    if kind_key == "vote":
        return (
            select(VoteRequest)
            .where(VoteRequest.status == RequestStatus.PENDING)
            .order_by(VoteRequest.created_at)
        )
    if kind_key == "uni":
        return (
            select(UniversityRequest)
            .where(UniversityRequest.status == RequestStatus.PENDING)
            .order_by(UniversityRequest.created_at)
        )
    if kind_key == "alias":
        return (
            select(AliasSuggestion)
            .where(AliasSuggestion.status == RequestStatus.PENDING)
            .order_by(AliasSuggestion.created_at)
        )
    raise ValueError(f"Неизвестный вид заявок: {kind_key!r}")


def allowed(modules: set[str]) -> list[Kind]:
    """Виды заявок, открытые человеку с такими модулями прав."""
    return [kind for kind in KINDS if kind.module.value in modules]


async def count(session: AsyncSession, kind_key: str) -> int:
    """Сколько заявок этого вида ждут решения."""
    total = await session.scalar(
        select(func.count()).select_from(statement(kind_key).subquery())
    )
    return total or 0


async def counts(session: AsyncSession, modules: set[str]) -> dict[str, int]:
    """Счётчики по всем видам, открытым этому человеку."""
    return {kind.key: await count(session, kind.key) for kind in allowed(modules)}


def render_summary(totals: dict[str, int]) -> str:
    """Сводка очереди: по строке на вид заявок, пустые не показываем."""
    lines = "\n".join(
        texts.QUEUE_LINE.format(title=BY_KEY[key].title, count=total)
        for key, total in totals.items()
        if total
    )
    return texts.QUEUE_HEADER.format(lines=lines)


async def _card(session: AsyncSession, kind_key: str, row: object) -> Card:
    """Одна запись из базы — в карточку с теми же кнопками, что и в чате."""
    if kind_key == "reg":
        return Card(
            text=await registration_service.render_registration_card(session, row),
            keyboard=registration_review_kb(row.request_id),
        )
    if kind_key == "act":
        author = await session.get(User, row.tg_id) if row.tg_id else None
        return Card(
            text=activity_service.build_act_card(author, row),
            keyboard=act_review_kb(str(row.request_id)),
            photo_file_id=row.photo_file_id,
        )
    if kind_key == "vote":
        author = await session.get(User, row.tg_id) if row.tg_id else None
        return Card(
            text=activity_service.build_vote_card(
                author, row.question, list(row.options), row.is_anonymous
            ),
            keyboard=vote_review_kb(str(row.request_id)),
        )
    if kind_key == "uni":
        return Card(
            text=university_service.render_request_card(row),
            keyboard=university_request_review_kb(row.request_id),
        )
    if kind_key == "alias":
        university = await university_repo.get(session, row.university_id)
        name = university.canonical_name if university is not None else texts.UNI_GONE_LABEL
        return Card(
            text=university_service.render_alias_card(row, name),
            keyboard=alias_suggestion_review_kb(row.suggestion_id),
        )
    raise ValueError(f"Неизвестный вид заявок: {kind_key!r}")


async def cards(session: AsyncSession, kind_key: str, limit: int = PAGE) -> list[Card]:
    """Готовые карточки самых давних неразобранных заявок этого вида."""
    rows = list(await session.scalars(statement(kind_key).limit(limit)))
    return [await _card(session, kind_key, row) for row in rows]


async def send(bot: Bot, chat_id: int, batch: list[Card]) -> int:
    """Отправляет карточки в личку админу. Возвращает, сколько дошло.

    Недоставленная карточка не повод бросать остальные: заявка никуда не
    девается, и следующее нажатие «📥 Заявки» покажет её снова.
    """
    delivered = 0
    for card in batch:
        try:
            await notification_service.deliver_card(
                bot, chat_id, card.text, card.keyboard, card.photo_file_id
            )
        except TelegramAPIError:
            continue
        delivered += 1
    return delivered
