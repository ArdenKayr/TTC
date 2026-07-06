import uuid
from datetime import date, datetime, timedelta, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

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
            return "⛔ Доступ заблокирован."
        return "Вы уже зарегистрированы."
    if await registration_repo.has_pending(session, tg_id):
        return "Ваша заявка уже на рассмотрении. Ожидайте решения администраторов."
    next_allowed = await registration_repo.latest_next_allowed_attempt(session, tg_id)
    if next_allowed is not None and next_allowed > _utcnow():
        minutes_left = int((next_allowed - _utcnow()).total_seconds() // 60) + 1
        return f"⏳ Повторная подача заявки будет доступна через {minutes_left} мин."
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
        university_label += " ⚠️ (новый вуз, не из справочника)"
    username = f"@{applicant.username}" if applicant.username else "без юзернейма"
    card = (
        f"🆕 <b>Заявка на регистрацию</b> (попытка №{request.attempt_number})\n"
        f"👤 {form['full_name']}\n"
        f"🔗 {username} · id <code>{applicant.id}</code>\n"
        f"🎓 {university_label}\n"
        f"👥 Группа: {form['university_group']}\n"
        f"🎂 {request.birth_date.strftime('%d.%m.%Y')}"
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
        return False, "Заявка не найдена."
    claimed = await registration_repo.try_mark_processed(
        session, request_id, RequestStatus.APPROVED, admin.tg_id, _utcnow()
    )
    if not claimed:
        return False, "Заявка уже обработана другим админом."

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
            invite_line = (
                "\n\nСсылка для вступления в группу (одноразовая, действует 15 минут):\n"
                f"{link.invite_link}"
            )
        except TelegramAPIError:
            notes.append("⚠️ Не удалось создать инвайт-ссылку (проверьте права бота в группе).")
    else:
        notes.append("⚠️ GROUP_CHAT_ID не настроен — инвайт-ссылка не создана.")

    delivered = await notification_service.dm_user(
        bot, request.tg_id, "🎉 Ваша заявка одобрена! Добро пожаловать." + invite_line
    )
    if not delivered:
        notes.append("⚠️ Не удалось отправить сообщение пользователю.")

    await audit_repo.add(
        session,
        AuditAction.REGISTRATION_APPROVED,
        actor_tg_id=admin.tg_id,
        target_tg_id=request.tg_id,
        target_entity_type="registration_request",
        target_entity_id=str(request_id),
    )
    await session.commit()

    result = f"✅ Принята — {admin.display_name}"
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
        return False, "Заявка не найдена."
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
        return False, "Заявка уже обработана другим админом."
    if reason:
        request.admin_comment = reason

    text = "К сожалению, ваша заявка отклонена."
    if reason:
        text += f"\nПричина: {reason}"
    if timeout > 0:
        text += f"\nПовторная подача будет доступна через {timeout} мин."
    else:
        text += "\nВы можете подать заявку повторно: /register"
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
    return True, f"❌ Отклонена — {admin.display_name}"
