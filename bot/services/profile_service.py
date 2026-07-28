"""Мой профиль: карточка, изменение полей, удаление аккаунта.

Удаление — «стереть личное, обезличить следы»: строка users и все
собственные заявки человека удаляются, активные мероприятия отменяются
(с пометкой в Афише), а там, где он фигурировал как решавший админ или
действующее лицо аудита, ссылка зануляется — журнал не разрушается
(остаётся безымянный tg_id в target-полях).
"""

from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.config import settings
from bot.db.models import (
    Activity,
    ActivityRequest,
    AliasSuggestion,
    AuditLog,
    ContentBlock,
    RegistrationRequest,
    UniversityRequest,
    User,
    VoteRequest,
)
from bot.db.repositories import audit_repo
from bot.enums import ActivityStatus, ActorType, AuditAction, UserRole
from bot.services import activity_service, error_service, notification_service


async def render_profile(session: AsyncSession, user: User) -> str:
    university = texts.PROFILE_NO_UNI
    if user.university_id is not None:
        from bot.db.models import University

        uni = await session.get(University, user.university_id)
        if uni is not None:
            university = escape(uni.canonical_name)
    username = f"@{user.username}" if user.username else texts.PROFILE_EMPTY_FIELD
    return texts.PROFILE_CARD.format(
        nick=escape(user.display_name),
        username=escape(username),
        tg_id=user.tg_id,
        university=university,
        group=escape(user.university_group) if user.university_group else texts.PROFILE_EMPTY_FIELD,
        birth=user.birth_date.strftime("%d.%m.%Y") if user.birth_date else texts.PROFILE_EMPTY_FIELD,
        about=escape(user.about_text) if user.about_text else texts.PROFILE_EMPTY_FIELD,
        role=texts.ROLE_LABELS.get(user.current_role, user.current_role.value),
        since=user.registration_date.strftime("%d.%m.%Y") if user.registration_date else "?",
    )


async def log_profile_update(session: AsyncSession, user: User, field: str) -> None:
    await audit_repo.add(
        session,
        AuditAction.PROFILE_UPDATED,
        actor_tg_id=user.tg_id,
        target_tg_id=user.tg_id,
        target_entity_type="user",
        target_entity_id=str(user.tg_id),
        meta={"field": field},
    )
    await session.commit()


async def delete_account(session: AsyncSession, bot: Bot, user: User) -> None:
    tg_id = user.tg_id

    # 1. Мероприятия: активные отменяем с пометкой в Афише, затем удаляем строки.
    activities = list(
        await session.scalars(select(Activity).where(Activity.organizer_id == tg_id))
    )
    for activity in activities:
        if activity.status == ActivityStatus.ACTIVE:
            activity.status = ActivityStatus.CANCELLED
            if activity.afisha_message_id is not None:
                await notification_service.edit_afisha_card(
                    bot,
                    activity.afisha_message_id,
                    activity_service._afisha_text(activity, user),
                )
        await session.delete(activity)
    await session.flush()

    # 2. Собственные заявки и анкеты.
    await session.execute(delete(ActivityRequest).where(ActivityRequest.tg_id == tg_id))
    await session.execute(delete(VoteRequest).where(VoteRequest.tg_id == tg_id))
    await session.execute(delete(RegistrationRequest).where(RegistrationRequest.tg_id == tg_id))
    await session.execute(delete(AliasSuggestion).where(AliasSuggestion.tg_id == tg_id))
    await session.execute(delete(UniversityRequest).where(UniversityRequest.tg_id == tg_id))

    # 3. Обезличить следы, где он был решавшим админом или автором изменений.
    for model, column in (
        (RegistrationRequest, RegistrationRequest.processed_by),
        (UniversityRequest, UniversityRequest.processed_by),
        (AliasSuggestion, AliasSuggestion.processed_by),
        (ActivityRequest, ActivityRequest.processed_by),
        (VoteRequest, VoteRequest.processed_by),
        (ContentBlock, ContentBlock.updated_by),
        (AuditLog, AuditLog.actor_tg_id),
    ):
        await session.execute(update(model).where(column == tg_id).values({column.key: None}))

    # 4. Запись в аудит (действие системное: строки пользователя больше нет).
    await audit_repo.add(
        session,
        AuditAction.ACCOUNT_DELETED,
        actor_tg_id=None,
        actor_type=ActorType.SYSTEM,
        target_tg_id=tg_id,
        target_entity_type="user",
        target_entity_id=str(tg_id),
    )

    # 5. Удалить сам профиль.
    await session.delete(user)
    await session.commit()

    # 6. Исключить из группы (ban+unban: выкинут, но сможет вернуться
    #    по новой инвайт-ссылке после повторной регистрации).
    if settings.group_chat_id is not None and user.current_role != UserRole.BANNED:
        try:
            await bot.ban_chat_member(settings.group_chat_id, tg_id)
            await bot.unban_chat_member(settings.group_chat_id, tg_id, only_if_banned=True)
        except TelegramAPIError as e:
            await error_service.report_issue(
                bot,
                source="Удаление аккаунта",
                tg_id=tg_id,
                note=f"Профиль удалён из базы, но исключить из группы не удалось: {e}",
            )
