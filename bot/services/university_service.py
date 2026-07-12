"""Заявки на добавление вуза и предложения вариантов поиска (сокращений).

Оба типа заявок попадают карточками в топик «Заявки» админского чата.
Любой админ может принять, отклонить или исправить данные (убрать опечатки)
до принятия решения. Решение атомарное: двум админам одновременно «принять»
не даст.
"""

import uuid
from datetime import datetime, timezone
from html import escape

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.db.models import AliasSuggestion, University, UniversityRequest, User
from bot.db.repositories import (
    alias_suggestion_repo,
    audit_repo,
    registration_repo,
    university_repo,
    university_request_repo,
)
from bot.enums import AuditAction, RequestStatus
from bot.keyboards.admin_kb import alias_suggestion_review_kb
from bot.services import notification_service, registration_service


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _username_label(username: str | None) -> str:
    return f"@{username}" if username else texts.USERNAME_MISSING


def render_request_card(request: UniversityRequest) -> str:
    aliases = ", ".join(escape(a) for a in (request.aliases or []))
    return texts.UNI_REQ_CARD.format(
        name=escape(request.applicant_name),
        username=escape(_username_label(request.applicant_username)),
        tg_id=request.tg_id,
        uni_name=escape(request.name),
        aliases=aliases or texts.NO_ALIASES_PLACEHOLDER,
        link=escape(request.link),
    )


def render_alias_card(suggestion: AliasSuggestion, university_name: str) -> str:
    return texts.ALIAS_SUG_CARD.format(
        university=escape(university_name),
        alias=escape(suggestion.alias_text),
        name=escape(suggestion.applicant_name),
        username=escape(_username_label(suggestion.applicant_username)),
        tg_id=suggestion.tg_id,
    )


async def submit_alias_suggestion(
    session: AsyncSession,
    bot: Bot,
    *,
    tg_id: int,
    applicant_name: str,
    applicant_username: str | None,
    university: University,
    alias_text: str,
) -> AliasSuggestion:
    """Создаёт предложение варианта поиска и шлёт карточку админам."""
    suggestion = AliasSuggestion(
        university_id=university.university_id,
        tg_id=tg_id,
        applicant_name=applicant_name,
        applicant_username=applicant_username,
        alias_text=alias_text,
    )
    session.add(suggestion)
    await session.flush()
    await notification_service.send_admin_card(
        bot,
        render_alias_card(suggestion, university.canonical_name),
        alias_suggestion_review_kb(suggestion.suggestion_id),
    )
    await session.commit()
    return suggestion


async def approve_request(
    session: AsyncSession, bot: Bot, request_id: uuid.UUID, admin: User
) -> tuple[bool, str]:
    """Одобряет заявку на вуз: создаёт вуз с вариантами, затем отправляет
    админам отложенную карточку регистрации заявителя."""
    request = await university_request_repo.get(session, request_id)
    if request is None:
        return False, texts.REVIEW_NOT_FOUND
    claimed = await university_request_repo.try_mark_processed(
        session, request_id, RequestStatus.APPROVED, admin.tg_id, _utcnow()
    )
    if not claimed:
        return False, texts.REVIEW_ALREADY_PROCESSED

    university = await university_repo.find_by_exact_name(session, request.name)
    if university is None:
        university = await university_repo.create_verified(session, request.name)
    for alias in request.aliases or []:
        if not await university_repo.alias_exists(session, university.university_id, alias):
            await university_repo.add_alias(session, university.university_id, alias)
    request.created_university_id = university.university_id

    registration = await registration_repo.get_pending_by_university_request(session, request_id)
    if registration is not None:
        registration.university_id = university.university_id

    await audit_repo.add(
        session,
        AuditAction.UNIVERSITY_REQUEST_APPROVED,
        actor_tg_id=admin.tg_id,
        target_tg_id=request.tg_id,
        target_entity_type="university_request",
        target_entity_id=str(request_id),
        meta={
            "university_id": university.university_id,
            "name": university.canonical_name,
            "aliases": list(request.aliases or []),
        },
    )
    await notification_service.dm_user(
        bot, request.tg_id, texts.UNI_ADDED_DM.format(university=escape(university.canonical_name))
    )
    if registration is not None:
        await registration_service.send_registration_card(
            session,
            bot,
            registration,
            university_line=university.canonical_name + texts.REG_CARD_UNI_FROM_REQUEST,
        )
    await session.commit()
    return True, texts.UNI_REQ_APPROVED_NOTE.format(admin=admin.display_name)


async def reject_request(
    session: AsyncSession,
    bot: Bot,
    request_id: uuid.UUID,
    admin: User,
    reason: str | None = None,
) -> tuple[bool, str]:
    """Отклоняет заявку на вуз. Карточка регистрации заявителя всё равно уходит
    админам — с пометкой, что вуз отклонён (решают по человеку вручную)."""
    request = await university_request_repo.get(session, request_id)
    if request is None:
        return False, texts.REVIEW_NOT_FOUND
    claimed = await university_request_repo.try_mark_processed(
        session, request_id, RequestStatus.REJECTED, admin.tg_id, _utcnow()
    )
    if not claimed:
        return False, texts.REVIEW_ALREADY_PROCESSED
    if reason:
        request.admin_comment = reason

    registration = await registration_repo.get_pending_by_university_request(session, request_id)

    dm_text = texts.UNI_REJECTED_DM.format(university=escape(request.name))
    if reason:
        dm_text += texts.REJECTED_DM_REASON.format(reason=escape(reason))
    if registration is not None:
        dm_text += texts.UNI_REJECTED_DM_REG_NOTE
    await notification_service.dm_user(bot, request.tg_id, dm_text)

    await audit_repo.add(
        session,
        AuditAction.UNIVERSITY_REQUEST_REJECTED,
        actor_tg_id=admin.tg_id,
        target_tg_id=request.tg_id,
        target_entity_type="university_request",
        target_entity_id=str(request_id),
        reason=reason,
        meta={"name": request.name},
    )
    if registration is not None:
        await registration_service.send_registration_card(
            session,
            bot,
            registration,
            university_line=texts.REG_CARD_UNI_REJECTED.format(name=request.name),
        )
    await session.commit()
    return True, texts.UNI_REQ_REJECTED_NOTE.format(admin=admin.display_name)


async def edit_request_data(
    session: AsyncSession,
    request_id: uuid.UUID,
    name: str,
    aliases: list[str],
    admin: User,
) -> tuple[bool, str | None]:
    """Правка данных заявки на вуз админом (до решения). False — уже обработана."""
    ok = await university_request_repo.update_pending_data(session, request_id, name, aliases)
    if not ok:
        return False, texts.REVIEW_ALREADY_PROCESSED
    await audit_repo.add(
        session,
        AuditAction.UNIVERSITY_REQUEST_EDITED,
        actor_tg_id=admin.tg_id,
        target_entity_type="university_request",
        target_entity_id=str(request_id),
        meta={"name": name, "aliases": aliases},
    )
    await session.commit()
    return True, None


async def approve_alias(
    session: AsyncSession, bot: Bot, suggestion_id: uuid.UUID, admin: User
) -> tuple[bool, str]:
    suggestion = await alias_suggestion_repo.get(session, suggestion_id)
    if suggestion is None:
        return False, texts.REVIEW_NOT_FOUND
    university = await university_repo.get(session, suggestion.university_id)
    if university is None:
        return False, texts.REVIEW_NOT_FOUND
    claimed = await alias_suggestion_repo.try_mark_processed(
        session, suggestion_id, RequestStatus.APPROVED, admin.tg_id, _utcnow()
    )
    if not claimed:
        return False, texts.REVIEW_ALREADY_PROCESSED

    duplicate = await university_repo.alias_exists(
        session, university.university_id, suggestion.alias_text
    )
    if not duplicate:
        await university_repo.add_alias(session, university.university_id, suggestion.alias_text)

    await audit_repo.add(
        session,
        AuditAction.ALIAS_APPROVED,
        actor_tg_id=admin.tg_id,
        target_tg_id=suggestion.tg_id,
        target_entity_type="alias_suggestion",
        target_entity_id=str(suggestion_id),
        meta={
            "university_id": university.university_id,
            "alias": suggestion.alias_text,
            "duplicate": duplicate,
        },
    )
    await notification_service.dm_user(
        bot,
        suggestion.tg_id,
        texts.ALIAS_ADDED_DM.format(
            alias=escape(suggestion.alias_text), university=escape(university.canonical_name)
        ),
    )
    await session.commit()
    note = texts.ALIAS_APPROVED_NOTE.format(admin=admin.display_name)
    if duplicate:
        note += texts.ALIAS_DUP_NOTE
    return True, note


async def reject_alias(
    session: AsyncSession, bot: Bot, suggestion_id: uuid.UUID, admin: User
) -> tuple[bool, str]:
    suggestion = await alias_suggestion_repo.get(session, suggestion_id)
    if suggestion is None:
        return False, texts.REVIEW_NOT_FOUND
    claimed = await alias_suggestion_repo.try_mark_processed(
        session, suggestion_id, RequestStatus.REJECTED, admin.tg_id, _utcnow()
    )
    if not claimed:
        return False, texts.REVIEW_ALREADY_PROCESSED
    await audit_repo.add(
        session,
        AuditAction.ALIAS_REJECTED,
        actor_tg_id=admin.tg_id,
        target_tg_id=suggestion.tg_id,
        target_entity_type="alias_suggestion",
        target_entity_id=str(suggestion_id),
        meta={"university_id": suggestion.university_id, "alias": suggestion.alias_text},
    )
    await session.commit()
    return True, texts.ALIAS_REJECTED_NOTE.format(admin=admin.display_name)


async def edit_alias_text(
    session: AsyncSession, suggestion_id: uuid.UUID, alias_text: str, admin: User
) -> tuple[bool, str | None]:
    """Правка текста предложенного варианта админом. False — уже обработано."""
    ok = await alias_suggestion_repo.update_pending_text(session, suggestion_id, alias_text)
    if not ok:
        return False, texts.REVIEW_ALREADY_PROCESSED
    await audit_repo.add(
        session,
        AuditAction.ALIAS_EDITED,
        actor_tg_id=admin.tg_id,
        target_entity_type="alias_suggestion",
        target_entity_id=str(suggestion_id),
        meta={"alias": alias_text},
    )
    await session.commit()
    return True, None
