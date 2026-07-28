import uuid
from datetime import date, datetime, timedelta, timezone
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.config import settings
from bot.db.models import RegistrationRequest, UniversityRequest, User
from bot.db.repositories import audit_repo, registration_repo, university_repo, user_repo
from bot.enums import AuditAction, RequestStatus, UserRole
from bot.keyboards.admin_kb import registration_review_kb, university_request_review_kb
from bot.services import error_service, notification_service, scenario_service
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
    """Создаёт заявку на регистрацию по данным анкеты.

    Три ветки по вузу (form["uni_mode"]):
    - "picked" — вуз выбран из справочника: карточка регистрации уходит админам сразу;
    - "new"    — человек подал заявку на новый вуз: сначала админам уходит карточка
                 вуза, карточка регистрации отправится после решения по вузу;
    - "none"   — не учится в вузе СПб: карточка сразу, с текстом «о себе».
    """
    uni_mode = form.get("uni_mode", "picked")
    university_id = form.get("university_id")
    university_line = form.get("university_name")
    university_request: UniversityRequest | None = None

    if uni_mode == "new":
        existing = await university_repo.find_by_exact_name(session, form["new_uni_name"])
        if existing is not None:
            # Такой вуз уже есть в справочнике — заявка на вуз не нужна.
            university_id = existing.university_id
            university_line = existing.canonical_name
            uni_mode = "picked"
        else:
            university_request = UniversityRequest(
                tg_id=applicant.id,
                applicant_name=form["nick"],
                applicant_username=applicant.username,
                name=form["new_uni_name"],
                aliases=form.get("new_uni_aliases") or [],
                link=form["new_uni_link"],
            )
            session.add(university_request)
            await session.flush()

    request = RegistrationRequest(
        tg_id=applicant.id,
        full_name=form["nick"],
        university_id=university_id,
        university_group=form.get("university_group"),
        birth_date=date.fromisoformat(form["birth_date"]),
        about_text=form.get("about_text"),
        university_request_id=(
            university_request.request_id if university_request is not None else None
        ),
        raw_input_snapshot={
            "username": applicant.username,
            "university_query": form.get("university_query"),
            "uni_mode": uni_mode,
            "new_university_name": form.get("new_uni_name"),
        },
        attempt_number=await registration_repo.next_attempt_number(session, applicant.id),
    )
    session.add(request)
    await session.flush()

    if university_request is not None:
        # Lazy import: university_service импортирует этот модуль на уровне модуля.
        from bot.services import university_service

        await notification_service.send_admin_card(
            bot,
            university_service.render_request_card(university_request),
            university_request_review_kb(university_request.request_id),
        )
    else:
        await send_registration_card(session, bot, request, university_line=university_line)
    await session.commit()
    return request


async def send_registration_card(
    session: AsyncSession,
    bot: Bot,
    request: RegistrationRequest,
    university_line: str | None = None,
) -> None:
    """Отправляет карточку заявки в топик «Заявки».

    university_line — готовая строка о вузе (например, с пометкой «добавлен по
    заявке» или «отклонён»). Если не передана — берётся название по
    university_id; если вуза нет вовсе — строка «Не учусь в вузе СПб».
    """
    snapshot = request.raw_input_snapshot or {}
    raw_username = snapshot.get("username")
    username = f"@{raw_username}" if raw_username else texts.USERNAME_MISSING
    if university_line is None and request.university_id is not None:
        university = await university_repo.get(session, request.university_id)
        if university is not None:
            university_line = university.canonical_name

    lines = [texts.SUM_NICK.format(nick=escape(request.full_name))]
    if university_line is not None:
        lines.append(texts.SUM_UNI.format(university=escape(university_line)))
    else:
        lines.append(texts.SUM_UNI_NONE)
    if request.university_group:
        lines.append(texts.SUM_GROUP.format(group=escape(request.university_group)))
    if request.about_text:
        lines.append(texts.SUM_ABOUT.format(about=escape(request.about_text)))
    lines.append(texts.SUM_BIRTH.format(birth_date=request.birth_date.strftime("%d.%m.%Y")))

    header = texts.REG_CARD_HEADER.format(
        attempt=request.attempt_number, username=escape(username), tg_id=request.tg_id
    )
    await notification_service.send_admin_card(
        bot, header + "\n" + "\n".join(lines), registration_review_kb(request.request_id)
    )


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
        about_text=request.about_text,
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
        except TelegramAPIError as e:
            notes.append(texts.NOTE_LINK_FAILED)
            await error_service.report_issue(
                bot,
                source="Регистрация: одобрение",
                tg_id=request.tg_id,
                note=f"Не удалось создать инвайт-ссылку: {e}",
            )
    else:
        notes.append(texts.NOTE_GROUP_NOT_SET)
        await error_service.report_issue(
            bot,
            source="Регистрация: одобрение",
            tg_id=request.tg_id,
            note="GROUP_CHAT_ID не настроен — инвайт-ссылка не создана.",
        )

    delivered = await scenario_service.dm(
        bot, session, request.tg_id, "reg_approved", suffix=invite_line
    )
    if not delivered:
        notes.append(texts.NOTE_DM_FAILED)
        await error_service.report_issue(
            bot,
            source="Регистрация: одобрение",
            tg_id=request.tg_id,
            note="Человек одобрен, но приветствие со ссылкой ему не доставилось "
            "(вероятно, ни разу не писал боту).",
        )

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

    suffix = ""
    if reason:
        suffix += texts.REJECTED_DM_REASON.format(reason=reason)
    if timeout > 0:
        suffix += texts.REJECTED_DM_TIMEOUT.format(minutes=timeout)
    else:
        suffix += texts.REJECTED_DM_RETRY
    delivered = await scenario_service.dm(
        bot, session, request.tg_id, "reg_rejected", suffix=suffix
    )
    if not delivered:
        await error_service.report_issue(
            bot,
            source="Регистрация: отказ",
            tg_id=request.tg_id,
            note="Человеку отказано, но сообщение об отказе не доставилось.",
        )

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
