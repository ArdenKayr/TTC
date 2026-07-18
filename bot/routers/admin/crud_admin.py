"""CRUD-панель (кнопка «CRUD» в Админстве): таблицы → записи → поля.

Владелец видит все таблицы, суперадмины — разрешённый список; users
для суперадминов только на чтение (роли — через панель «Пользователи»).
Каждое изменение уходит в audit_log с old/new значениями.
"""

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.db.models import User
from bot.db.repositories import audit_repo
from bot.enums import AuditAction, UserRole
from bot.filters.role_filter import IsSuperadmin
from bot.keyboards.callback_data import (
    CrudCancelCB,
    CrudDelCB,
    CrudFieldCB,
    CrudHomeCB,
    CrudNewCB,
    CrudPageCB,
    CrudRowCB,
    CrudTableCB,
    NoopCB,
)
from bot.keyboards.common_kb import MENU_BUTTON_TEXTS as _MENU_BUTTONS
from bot.routers.common import send_start_screen
from bot.services import crud_service
from bot.states.content_states import CrudForm

router = Router(name="crud_admin")
router.message.filter(IsSuperadmin())
router.callback_query.filter(IsSuperadmin())

_PRIVATE = F.chat.type == ChatType.PRIVATE


def _tables_kb(user: User) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for spec in crud_service.specs_for(user):
        row.append(
            InlineKeyboardButton(
                text=spec.title, callback_data=CrudTableCB(t=spec.code).pack()
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _spec_or_alert(
    callback: CallbackQuery, code: str, db_user: User
) -> crud_service.TableSpec | None:
    spec = crud_service.TABLES.get(code)
    if spec is None:
        await callback.answer(texts.CRUD_NOT_FOUND, show_alert=True)
        return None
    if not crud_service.can_view(db_user, spec):
        await callback.answer(texts.CRUD_NO_ACCESS, show_alert=True)
        return None
    return spec


async def _list_view(
    session: AsyncSession, spec: crud_service.TableSpec, page: int, db_user: User
) -> tuple[str, InlineKeyboardMarkup]:
    total = await crud_service.count(session, spec)
    pages = max(1, -(-total // crud_service.PAGE_SIZE))
    page = max(0, min(page, pages - 1))
    rows = await crud_service.page_rows(session, spec, page)

    if not rows:
        text = texts.CRUD_LIST_EMPTY.format(title=spec.title)
    else:
        lines = [
            texts.CRUD_LIST_HEADER.format(
                title=spec.title, page=page + 1, pages=pages, total=total
            )
        ]
        lines += [
            f"<b>{i + 1}.</b> {crud_service.fmt_value(spec.label(obj), 60)}"
            for i, obj in enumerate(rows)
        ]
        text = "\n".join(lines)

    kb_rows: list[list[InlineKeyboardButton]] = []
    number_row: list[InlineKeyboardButton] = []
    pk_name = crud_service.pk_col(spec).key
    for i, obj in enumerate(rows):
        number_row.append(
            InlineKeyboardButton(
                text=str(i + 1),
                callback_data=CrudRowCB(
                    t=spec.code, pk=str(getattr(obj, pk_name)), page=page
                ).pack(),
            )
        )
        if len(number_row) == 4:
            kb_rows.append(number_row)
            number_row = []
    if number_row:
        kb_rows.append(number_row)
    if pages > 1:
        kb_rows.append(
            [
                InlineKeyboardButton(
                    text=texts.BTN.UNI_PAGE_PREV,
                    callback_data=CrudPageCB(t=spec.code, page=page - 1).pack()
                    if page > 0
                    else NoopCB().pack(),
                ),
                InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data=NoopCB().pack()),
                InlineKeyboardButton(
                    text=texts.BTN.UNI_PAGE_NEXT,
                    callback_data=CrudPageCB(t=spec.code, page=page + 1).pack()
                    if page < pages - 1
                    else NoopCB().pack(),
                ),
            ]
        )
    last_row = [
        InlineKeyboardButton(text=texts.BTN.CRUD_BACK_TABLES, callback_data=CrudHomeCB().pack())
    ]
    if spec.create_fields and crud_service.can_write(db_user, spec):
        last_row.append(
            InlineKeyboardButton(
                text=texts.BTN.CRUD_CREATE, callback_data=CrudNewCB(t=spec.code).pack()
            )
        )
    kb_rows.append(last_row)
    return text, InlineKeyboardMarkup(inline_keyboard=kb_rows)


async def _detail_view(
    spec: crud_service.TableSpec, obj, page: int, db_user: User
) -> tuple[str, InlineKeyboardMarkup]:
    pk_name = crud_service.pk_col(spec).key
    pk = str(getattr(obj, pk_name))
    header = texts.CRUD_ROW_HEADER.format(title=spec.title, pk=pk)
    text = crud_service.render_detail(spec, obj, header)

    kb_rows: list[list[InlineKeyboardButton]] = []
    writable = crud_service.can_write(db_user, spec)
    if writable:
        row: list[InlineKeyboardButton] = []
        for i, col in enumerate(crud_service.columns(spec)):
            if col.primary_key:
                continue
            row.append(
                InlineKeyboardButton(
                    text=f"✏️ {col.name}",
                    callback_data=CrudFieldCB(t=spec.code, pk=pk, i=i).pack(),
                )
            )
            if len(row) == 2:
                kb_rows.append(row)
                row = []
        if row:
            kb_rows.append(row)
        kb_rows.append(
            [
                InlineKeyboardButton(
                    text=texts.BTN.CRUD_DELETE,
                    callback_data=CrudDelCB(t=spec.code, pk=pk).pack(),
                )
            ]
        )
    else:
        text += texts.CRUD_READ_ONLY_NOTE
    kb_rows.append(
        [
            InlineKeyboardButton(
                text=texts.BTN.CRUD_BACK_LIST,
                callback_data=CrudPageCB(t=spec.code, page=page).pack(),
            )
        ]
    )
    return text, InlineKeyboardMarkup(inline_keyboard=kb_rows)


def _cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.BTN.CONTENT_CANCEL, callback_data=CrudCancelCB().pack())]
        ]
    )


# --- Вход и навигация ---


@router.message(_PRIVATE, StateFilter(None), F.text == texts.BTN.ADMIN_PANEL_CRUD)
async def crud_home(message: Message, db_user: User) -> None:
    await message.answer(texts.CRUD_PICK_TABLE, reply_markup=_tables_kb(db_user))


@router.callback_query(CrudHomeCB.filter())
async def cb_home(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    await state.clear()
    await callback.message.edit_text(texts.CRUD_PICK_TABLE, reply_markup=_tables_kb(db_user))
    await callback.answer()


@router.callback_query(CrudTableCB.filter())
async def cb_table(
    callback: CallbackQuery, callback_data: CrudTableCB, session: AsyncSession, db_user: User
) -> None:
    spec = await _spec_or_alert(callback, callback_data.t, db_user)
    if spec is None:
        return
    text, kb = await _list_view(session, spec, 0, db_user)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(CrudPageCB.filter())
async def cb_page(
    callback: CallbackQuery, callback_data: CrudPageCB, session: AsyncSession, db_user: User
) -> None:
    spec = await _spec_or_alert(callback, callback_data.t, db_user)
    if spec is None:
        return
    text, kb = await _list_view(session, spec, callback_data.page, db_user)
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:  # текст не изменился
        pass
    await callback.answer()


@router.callback_query(CrudRowCB.filter())
async def cb_row(
    callback: CallbackQuery, callback_data: CrudRowCB, session: AsyncSession, db_user: User
) -> None:
    spec = await _spec_or_alert(callback, callback_data.t, db_user)
    if spec is None:
        return
    obj = await crud_service.get_row(session, spec, callback_data.pk)
    if obj is None:
        await callback.answer(texts.CRUD_NOT_FOUND, show_alert=True)
        return
    text, kb = await _detail_view(spec, obj, callback_data.page, db_user)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# --- Изменение поля ---


@router.callback_query(CrudFieldCB.filter())
async def cb_field(
    callback: CallbackQuery,
    callback_data: CrudFieldCB,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    spec = await _spec_or_alert(callback, callback_data.t, db_user)
    if spec is None:
        return
    if not crud_service.can_write(db_user, spec):
        alert = texts.CRUD_USERS_GUARD if spec.write_owner_only else texts.CRUD_NO_ACCESS
        await callback.answer(alert, show_alert=True)
        return
    cols = crud_service.columns(spec)
    if not 0 <= callback_data.i < len(cols):
        await callback.answer(texts.CRUD_NOT_FOUND, show_alert=True)
        return
    obj = await crud_service.get_row(session, spec, callback_data.pk)
    if obj is None:
        await callback.answer(texts.CRUD_NOT_FOUND, show_alert=True)
        return
    col = cols[callback_data.i]
    await state.set_state(CrudForm.value)
    await state.update_data(t=spec.code, pk=callback_data.pk, i=callback_data.i)
    await callback.message.answer(
        texts.CRUD_EDIT_PROMPT.format(
            field=col.name,
            value=crud_service.fmt_value(getattr(obj, col.key)),
            hint=crud_service.value_hint(col),
        ),
        reply_markup=_cancel_kb(),
    )
    await callback.answer()


@router.message(CrudForm.value, F.text.in_(_MENU_BUTTONS))
@router.message(CrudForm.create, F.text.in_(_MENU_BUTTONS))
async def crud_menu_pressed(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.CRUD_CANCELLED)


@router.message(StateFilter(CrudForm), CommandStart())
async def crud_start_over(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User | None
) -> None:
    await state.clear()
    await send_start_screen(message, session, db_user)


@router.message(CrudForm.value, F.text, ~F.text.startswith("/"))
async def crud_new_value(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    data = await state.get_data()
    spec = crud_service.TABLES.get(data["t"])
    if spec is None or not crud_service.can_write(db_user, spec):
        await state.clear()
        await message.answer(texts.CRUD_CANCELLED)
        return
    col = crud_service.columns(spec)[data["i"]]
    try:
        value = crud_service.parse_value(col, message.text)
    except ValueError as e:
        await message.answer(texts.CRUD_VALUE_INVALID.format(error=e))
        return
    obj = await crud_service.get_row(session, spec, data["pk"])
    if obj is None:
        await state.clear()
        await message.answer(texts.CRUD_NOT_FOUND)
        return
    old_value = getattr(obj, col.key)
    setattr(obj, col.key, value)
    await audit_repo.add(
        session,
        AuditAction.CRUD_UPDATED,
        actor_tg_id=db_user.tg_id,
        target_entity_type=spec.model.__tablename__,
        target_entity_id=data["pk"],
        meta={
            "field": col.name,
            "old": crud_service.audit_value(old_value),
            "new": crud_service.audit_value(value),
        },
    )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        await message.answer(texts.CRUD_VALUE_INVALID.format(error="нарушает ограничения БД"))
        return
    await state.clear()
    obj = await crud_service.get_row(session, spec, data["pk"])
    text, kb = await _detail_view(spec, obj, 0, db_user)
    await message.answer(text, reply_markup=kb)


# --- Удаление ---


@router.callback_query(CrudDelCB.filter())
async def cb_delete(
    callback: CallbackQuery, callback_data: CrudDelCB, session: AsyncSession, db_user: User
) -> None:
    spec = await _spec_or_alert(callback, callback_data.t, db_user)
    if spec is None:
        return
    if not crud_service.can_write(db_user, spec):
        alert = texts.CRUD_USERS_GUARD if spec.write_owner_only else texts.CRUD_NO_ACCESS
        await callback.answer(alert, show_alert=True)
        return
    obj = await crud_service.get_row(session, spec, callback_data.pk)
    if obj is None:
        await callback.answer(texts.CRUD_NOT_FOUND, show_alert=True)
        return
    if not callback_data.confirmed:
        await callback.message.answer(
            texts.CRUD_DELETE_CONFIRM.format(pk=callback_data.pk, title=spec.title),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=texts.BTN.CRUD_DELETE_YES,
                            callback_data=CrudDelCB(
                                t=spec.code, pk=callback_data.pk, confirmed=True
                            ).pack(),
                        ),
                        InlineKeyboardButton(
                            text=texts.BTN.CONTENT_CANCEL, callback_data=CrudCancelCB().pack()
                        ),
                    ]
                ]
            ),
        )
        await callback.answer()
        return
    await session.delete(obj)
    await audit_repo.add(
        session,
        AuditAction.CRUD_DELETED,
        actor_tg_id=db_user.tg_id,
        target_entity_type=spec.model.__tablename__,
        target_entity_id=callback_data.pk,
        meta={"label": spec.label(obj)},
    )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        await callback.message.answer(texts.CRUD_FK_BLOCKED)
        await callback.answer()
        return
    await callback.message.edit_text(texts.CRUD_DELETED)
    await callback.answer()


# --- Создание записи ---


async def _create_prompt(
    message: Message, spec: crud_service.TableSpec, field_name: str
) -> None:
    col = spec.model.__table__.columns[field_name]
    await message.answer(
        texts.CRUD_CREATE_PROMPT.format(
            title=spec.title, field=field_name, hint=crud_service.value_hint(col)
        ),
        reply_markup=_cancel_kb(),
    )


@router.callback_query(CrudNewCB.filter())
async def cb_new(
    callback: CallbackQuery,
    callback_data: CrudNewCB,
    state: FSMContext,
    db_user: User,
) -> None:
    spec = await _spec_or_alert(callback, callback_data.t, db_user)
    if spec is None:
        return
    if not spec.create_fields or not crud_service.can_write(db_user, spec):
        await callback.answer(texts.CRUD_NO_ACCESS, show_alert=True)
        return
    await state.set_state(CrudForm.create)
    await state.update_data(t=spec.code, idx=0, values={})
    await _create_prompt(callback.message, spec, spec.create_fields[0])
    await callback.answer()


@router.message(CrudForm.create, F.text, ~F.text.startswith("/"))
async def crud_create_value(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    data = await state.get_data()
    spec = crud_service.TABLES.get(data["t"])
    if spec is None or not crud_service.can_write(db_user, spec):
        await state.clear()
        await message.answer(texts.CRUD_CANCELLED)
        return
    field_name = spec.create_fields[data["idx"]]
    col = spec.model.__table__.columns[field_name]
    try:
        value = crud_service.parse_value(col, message.text)
    except ValueError as e:
        await message.answer(texts.CRUD_VALUE_INVALID.format(error=e))
        return
    values = data["values"]
    values[field_name] = value
    if data["idx"] + 1 < len(spec.create_fields):
        await state.update_data(idx=data["idx"] + 1, values=values)
        await _create_prompt(message, spec, spec.create_fields[data["idx"] + 1])
        return
    await state.clear()
    obj = spec.model(**values)
    session.add(obj)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        await message.answer(texts.CRUD_CREATE_FAILED.format(error="нарушает ограничения БД"))
        return
    pk = str(getattr(obj, crud_service.pk_col(spec).key))
    await audit_repo.add(
        session,
        AuditAction.CRUD_CREATED,
        actor_tg_id=db_user.tg_id,
        target_entity_type=spec.model.__tablename__,
        target_entity_id=pk,
        meta={"values": {k: crud_service.audit_value(v) for k, v in values.items()}},
    )
    await session.commit()
    await message.answer(texts.CRUD_CREATED)
    text, kb = await _detail_view(spec, obj, 0, db_user)
    await message.answer(text, reply_markup=kb)


@router.callback_query(CrudCancelCB.filter())
async def cb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(texts.CRUD_CANCELLED)
    await callback.answer()
