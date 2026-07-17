"""Мероприятия и голосования: одобрение заявок, Афиша, роль организатора.

Правило роли: одобрили мероприятие — автор с ролью «пользователь» становится
«организатором»; закрыли его последнее активное мероприятие — роль снимается.
Роли admin/custom никогда не трогаем.
"""

import uuid
from datetime import datetime, timezone
from html import escape

from aiogram import Bot
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot import limits, texts
from bot.db.models import Activity, ActivityRequest, User, VoteRequest
from bot.db.repositories import audit_repo
from bot.enums import ActivityStatus, AuditAction, RequestStatus, UserRole
from bot.services import notification_service


def parse_vote_options(raw: str) -> list[str] | None:
    """Варианты ответа из одного сообщения: по строке на вариант.

    Пустые строки пропускаются. None — если вариантов не 2–10
    или какой-то длиннее лимита Telegram.
    """
    options = [line.strip() for line in raw.splitlines() if line.strip()]
    if not limits.VOTE_OPTIONS_MIN <= len(options) <= limits.VOTE_OPTIONS_MAX:
        return None
    if any(len(option) > limits.VOTE_OPTION_MAX for option in options):
        return None
    return options


def user_label(user: User) -> str:
    username = f"@{user.username}" if user.username else f"id {user.tg_id}"
    return f"{escape(user.display_name)} ({username})"


def _url_line(extra_url: str | None) -> str:
    return texts.ACT_URL_LINE.format(url=escape(extra_url)) if extra_url else ""


def build_act_card(author: User, title: str, description: str, extra_url: str | None) -> str:
    username = f"@{author.username}" if author.username else f"id {author.tg_id}"
    return texts.ACT_CARD.format(
        name=escape(author.display_name),
        username=escape(username),
        title=escape(title),
        description=escape(description),
        url_line=_url_line(extra_url),
    )


def build_vote_card(author: User, question: str, options: list[str]) -> str:
    username = f"@{author.username}" if author.username else f"id {author.tg_id}"
    rows = "\n".join(texts.VOTE_OPTION_ROW.format(option=escape(option)) for option in options)
    return texts.VOTE_CARD.format(
        name=escape(author.display_name),
        username=escape(username),
        question=escape(question),
        options=rows,
    )


def _afisha_text(activity: Activity, organizer: User) -> str:
    status_line = ""
    if activity.status == ActivityStatus.COMPLETED:
        status_line = texts.AFISHA_DONE_LINE
    elif activity.status == ActivityStatus.CANCELLED:
        status_line = texts.AFISHA_CANCELLED_LINE
    return texts.AFISHA_CARD.format(
        status_line=status_line,
        title=escape(activity.title),
        description=escape(activity.description),
        url_line=_url_line(activity.extra_url),
        organizer=user_label(organizer),
    )


async def approve_activity(
    session: AsyncSession, bot: Bot, request_id: uuid.UUID, admin: User
) -> tuple[bool, str]:
    request = await session.get(ActivityRequest, request_id)
    if request is None or request.status != RequestStatus.PENDING:
        return False, texts.REVIEW_ALREADY_PROCESSED
    author = await session.get(User, request.tg_id)
    if author is None:
        return False, texts.USER_NOT_FOUND

    activity = Activity(
        organizer_id=request.tg_id,
        title=request.title,
        description=request.description,
        extra_url=request.extra_url,
        request_id=request.request_id,
    )
    session.add(activity)

    promoted = False
    if author.current_role == UserRole.USER:
        author.current_role = UserRole.ORGANIZER
        promoted = True
        await audit_repo.add(
            session,
            AuditAction.ORGANIZER_PROMOTED,
            actor_tg_id=admin.tg_id,
            target_tg_id=author.tg_id,
            target_entity_type="activity",
            target_entity_id=str(activity.activity_id),
        )

    notes = [texts.ACT_APPROVED_NOTE.format(admin=admin.display_name)]
    afisha_message_id = await notification_service.send_afisha_card(
        bot, _afisha_text(activity, author)
    )
    if afisha_message_id is None:
        notes.append(texts.NOTE_AFISHA_FAILED)
    activity.afisha_message_id = afisha_message_id

    request.status = RequestStatus.APPROVED
    request.processed_by = admin.tg_id
    request.processed_at = datetime.now(timezone.utc)
    await audit_repo.add(
        session,
        AuditAction.ACTIVITY_APPROVED,
        actor_tg_id=admin.tg_id,
        target_tg_id=author.tg_id,
        target_entity_type="activity_request",
        target_entity_id=str(request.request_id),
    )

    dm_text = texts.ACT_APPROVED_DM if promoted else texts.ACT_APPROVED_DM_ALREADY_ORG
    delivered = await notification_service.dm_user(
        bot, author.tg_id, dm_text.format(title=escape(request.title))
    )
    if not delivered:
        notes.append(texts.NOTE_DM_FAILED)

    await session.commit()
    return True, "\n".join(notes)


async def reject_activity(
    session: AsyncSession, bot: Bot, request_id: uuid.UUID, admin: User
) -> tuple[bool, str]:
    request = await session.get(ActivityRequest, request_id)
    if request is None or request.status != RequestStatus.PENDING:
        return False, texts.REVIEW_ALREADY_PROCESSED
    request.status = RequestStatus.REJECTED
    request.processed_by = admin.tg_id
    request.processed_at = datetime.now(timezone.utc)
    await audit_repo.add(
        session,
        AuditAction.ACTIVITY_REJECTED,
        actor_tg_id=admin.tg_id,
        target_tg_id=request.tg_id,
        target_entity_type="activity_request",
        target_entity_id=str(request.request_id),
    )
    notes = [texts.ACT_REJECTED_NOTE.format(admin=admin.display_name)]
    delivered = await notification_service.dm_user(
        bot, request.tg_id, texts.ACT_REJECTED_DM.format(title=escape(request.title))
    )
    if not delivered:
        notes.append(texts.NOTE_DM_FAILED)
    await session.commit()
    return True, "\n".join(notes)


async def approve_vote(
    session: AsyncSession, bot: Bot, request_id: uuid.UUID, admin: User
) -> tuple[bool, str]:
    request = await session.get(VoteRequest, request_id)
    if request is None or request.status != RequestStatus.PENDING:
        return False, texts.REVIEW_ALREADY_PROCESSED

    notes = [texts.VOTE_APPROVED_NOTE.format(admin=admin.display_name)]
    poll_message_id = await notification_service.send_vote_poll(
        bot, request.question, list(request.options)
    )
    if poll_message_id is None:
        notes.append(texts.NOTE_POLL_FAILED)
    request.poll_message_id = poll_message_id

    request.status = RequestStatus.APPROVED
    request.processed_by = admin.tg_id
    request.processed_at = datetime.now(timezone.utc)
    await audit_repo.add(
        session,
        AuditAction.VOTE_APPROVED,
        actor_tg_id=admin.tg_id,
        target_tg_id=request.tg_id,
        target_entity_type="vote_request",
        target_entity_id=str(request.request_id),
    )
    delivered = await notification_service.dm_user(
        bot, request.tg_id, texts.VOTE_APPROVED_DM.format(question=escape(request.question))
    )
    if not delivered:
        notes.append(texts.NOTE_DM_FAILED)
    await session.commit()
    return True, "\n".join(notes)


async def reject_vote(
    session: AsyncSession, bot: Bot, request_id: uuid.UUID, admin: User
) -> tuple[bool, str]:
    request = await session.get(VoteRequest, request_id)
    if request is None or request.status != RequestStatus.PENDING:
        return False, texts.REVIEW_ALREADY_PROCESSED
    request.status = RequestStatus.REJECTED
    request.processed_by = admin.tg_id
    request.processed_at = datetime.now(timezone.utc)
    await audit_repo.add(
        session,
        AuditAction.VOTE_REJECTED,
        actor_tg_id=admin.tg_id,
        target_tg_id=request.tg_id,
        target_entity_type="vote_request",
        target_entity_id=str(request.request_id),
    )
    notes = [texts.VOTE_REJECTED_NOTE.format(admin=admin.display_name)]
    delivered = await notification_service.dm_user(
        bot, request.tg_id, texts.VOTE_REJECTED_DM.format(question=escape(request.question))
    )
    if not delivered:
        notes.append(texts.NOTE_DM_FAILED)
    await session.commit()
    return True, "\n".join(notes)


async def list_active(session: AsyncSession) -> list[Activity]:
    result = await session.scalars(
        select(Activity)
        .where(Activity.status == ActivityStatus.ACTIVE)
        .order_by(Activity.created_at)
    )
    return list(result)


async def finish_activity(
    session: AsyncSession, bot: Bot, activity_id: uuid.UUID, admin: User, cancelled: bool
) -> tuple[bool, str]:
    """Завершение или отмена мероприятия: пометка в Афише + авто-снятие роли."""
    activity = await session.get(Activity, activity_id)
    if activity is None or activity.status != ActivityStatus.ACTIVE:
        return False, texts.ACT_GONE
    organizer = await session.get(User, activity.organizer_id)

    activity.status = ActivityStatus.CANCELLED if cancelled else ActivityStatus.COMPLETED
    if activity.afisha_message_id is not None and organizer is not None:
        await notification_service.edit_afisha_card(
            bot, activity.afisha_message_id, _afisha_text(activity, organizer)
        )

    demoted = False
    if organizer is not None and organizer.current_role == UserRole.ORGANIZER:
        remaining = await session.scalar(
            select(func.count())
            .select_from(Activity)
            .where(
                Activity.organizer_id == organizer.tg_id,
                Activity.status == ActivityStatus.ACTIVE,
                Activity.activity_id != activity.activity_id,
            )
        )
        if not remaining:
            organizer.current_role = UserRole.USER
            demoted = True
            await audit_repo.add(
                session,
                AuditAction.ORGANIZER_DEMOTED,
                actor_tg_id=admin.tg_id,
                target_tg_id=organizer.tg_id,
                target_entity_type="activity",
                target_entity_id=str(activity.activity_id),
            )

    action = AuditAction.ACTIVITY_CANCELLED if cancelled else AuditAction.ACTIVITY_COMPLETED
    await audit_repo.add(
        session,
        action,
        actor_tg_id=admin.tg_id,
        target_tg_id=activity.organizer_id,
        target_entity_type="activity",
        target_entity_id=str(activity.activity_id),
    )

    dm_text = texts.ACT_CANCELLED_DM if cancelled else texts.ACT_COMPLETED_DM
    dm = dm_text.format(title=escape(activity.title))
    if demoted:
        dm += "\n\n" + texts.ORG_DEMOTED_DM
    await notification_service.dm_user(bot, activity.organizer_id, dm)

    await session.commit()
    note = texts.ACT_CANCELLED_NOTE if cancelled else texts.ACT_COMPLETED_NOTE
    return True, note.format(admin=admin.display_name)
