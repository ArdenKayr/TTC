import uuid
from datetime import date, datetime, timedelta, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.config import settings
from bot.db.models import RegistrationRequest, User
from bot.db.repositories import audit_repo, registration_repo, university_repo, user_repo
from bot.enums import ActorType, AuditAction, RequestStatus, UserRole
from bot.keyboards.admin_kb import registration_review_kb
from bot.services import notification_service
from bot.services.throttle import rejection_timeout_minutes

INVITE_LINK_TTL = timedelta(minutes=15)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def check_can_apply(session: AsyncSession, tg_id: int) -> str | None:
    """Returns a user-facing error message, or None if applying is allowed."""
    user = await user_repo.get_by_tg_id(session, tg_id)
    if user is not None:
        if user.current_role == UserRole.BANNED:
            return texts.BANNED_ALERT
        return texts.APPLY_ALREADY_REGISTERED
    if await registration_repo.has_pending(session, tg_id):
        return texts.APPLY_PENDING
    next_allowed = await registration_repo.latest_next_allowed_attempt(session, tg_id)
    if next_allowed is not None and next_allowed > _utcnow():
        minutes_left = int((next_allowed - _utcnow()).total_seconds() // 60) + 1
        return texts.APPLY_THROTTLED.format(minutes=minutes_left)
    return None


async def submit_request(
    session: AsyncSession, bot: Bot, applicant: TgUser, form: dict
) -> RegistrationRequest:
    new_university_name = form.get("new_university_name")
    university_id = form.get("university_id")
    is_new_university = False
    if university_id is None:
        existing = await university_repo.find_by_exact_name(session, new_university_name)
        if existing is not None:
            university_id = existing.university_id
        else:
            university = await university_repo.create_unverified(session, new_university_name)
            university_id = university.university_id
            is_new_university = True
            await audit_repo.add(
                session,
                AuditAction.UNIVERSITY_ADDED,
                actor_type=ActorType.SYSTEM,
                target_entity_type="university",
                target_entity_id=str(university_id),
                meta={"name": new_university_name, "added_by_tg_id": applicant.id},
            )

    request = RegistrationRequest(
        tg_id=applicant.id,
        full_name=form["full_name"],
        university_id=university_id,
        university_group=form["university_group"],
        birth_date=date.fromisoformat(form["birth_date"]),
        raw_input_snapshot={
            "username": applicant.username,
            "university_query": form.get("university_query"),
            "new_university_name": new_university_name,
        },
        attempt_number=await registration_repo.next_attempt_number(session, applicant.id),
    )
    session.add(request)
    await session.flush()

    university_label = form.get("university_name") or new_university_name
    if is_new_university:
        university_label += texts.REG_CARD_NEW_UNI_SUFFIX
    username = f"@{applicant.username}" if applicant.username else texts.USERNAME_MISSING
    card = texts.REG_CARD.format(
        attempt=request.attempt_number,
        name=form["full_name"],
        username=username,
        tg_id=applicant.id,
        university=university_label,
        group=form["university_group"],
        birth_date=request.birth_date.strftime("%d.%m.%Y"),
    )
    await notification_service.send_admin_card(
        bot, card, registration_review_kb(request.request_id)
    )
    await session.commit()
    return request


async def approve(
    session: AsyncSession, bot: Bot, request_id: uuid.UUID, admin: User
) -> tuple[bool, str]:
    request = await registration_repo.get(session, request_id)
    if request is None:
        return False, texts.REVIEW_NOT_FOUND
    claimed = await registration_repo.try_mark_processed(
        session, request_id, RequestStatus.APPROVED, admin.tg_id, _utcnow()
    )
    if not claimed:
        return False, texts.REVIEW_ALREADY_PROCESSED

    snapshot = request.raw_input_snapshot or {}
    await user_repo.upsert_from_registration(
        session,
        tg_id=request.tg_id,
        username=snapshot.get("username"),
        display_name=request.full_name,
        university_id=request.university_id,
        university_group=request.university_group,
        birth_date=request.birth_date,
    )

    notes = []
    invite_line = ""
    if settings.group_chat_id is not None:
        try:
            link = await bot.create_chat_invite_link(
                settings.group_chat_id,
                name=f"reg:{request.tg_id}",
                expire_date=_utcnow() + INVITE_LINK_TTL,
                member_limit=1,
            )
            invite_line = texts.APPROVED_DM_INVITE.format(link=link.invite_link)
        except TelegramAPIError:
            notes.append(texts.NOTE_LINK_FAILED)
    else:
        notes.append(texts.NOTE_GROUP_NOT_SET)

    delivered = await notification_service.dm_user(
        bot, request.tg_id, texts.APPROVED_DM + invite_line
    )
    if not delivered:
        notes.append(texts.NOTE_DM_FAILED)

    await audit_repo.add(
        session,
        AuditAction.REGISTRATION_APPROVED,
        actor_tg_id=admin.tg_id,
        target_tg_id=request.tg_id,
        target_entity_type="registration_request",
        target_entity_id=str(request_id),
    )
    await session.commit()

    result = texts.CARD_APPROVED.format(admin=admin.display_name)
    if notes:
        result += "\n" + "\n".join(notes)
    return True, result


async def reject(
    session: AsyncSession,
    bot: Bot,
    request_id: uuid.UUID,
    admin: User,
    reason: str | None = None,
) -> tuple[bool, str]:
    request = await registration_repo.get(session, request_id)
    if request is None:
        return False, texts.REVIEW_NOT_FOUND
    timeout = rejection_timeout_minutes(request.attempt_number)
    now = _utcnow()
    claimed = await registration_repo.try_mark_processed(
        session,
        request_id,
        RequestStatus.REJECTED,
        admin.tg_id,
        now,
        next_allowed_attempt=now + timedelta(minutes=timeout),
    )
    if not claimed:
        return False, texts.REVIEW_ALREADY_PROCESSED
    if reason:
        request.admin_comment = reason

    text = texts.REJECTED_DM
    if reason:
        text += texts.REJECTED_DM_REASON.format(reason=reason)
    if timeout > 0:
        text += texts.REJECTED_DM_TIMEOUT.format(minutes=timeout)
    else:
        text += texts.REJECTED_DM_RETRY
    await notification_service.dm_user(bot, request.tg_id, text)

    await audit_repo.add(
        session,
        AuditAction.REGISTRATION_REJECTED,
        actor_tg_id=admin.tg_id,
        target_tg_id=request.tg_id,
        target_entity_type="registration_request",
        target_entity_id=str(request_id),
        reason=reason,
        meta={"attempt_number": request.attempt_number, "timeout_minutes": timeout},
    )
    await session.commit()
    return True, texts.CARD_REJECTED.format(admin=admin.display_name)
