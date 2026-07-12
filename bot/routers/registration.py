from datetime import date, datetime

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.db.repositories import university_repo
from bot.keyboards.callback_data import RegFormCB, UniversityNewCB, UniversityPickCB
from bot.keyboards.registration_kb import confirm_kb, university_results_kb
from bot.services import registration_service
from bot.states.registration_states import RegistrationForm

router = Router(name="registration")


@router.message(Command("register"), F.chat.type == ChatType.PRIVATE)
async def cmd_register(message: Message, session: AsyncSession, state: FSMContext) -> None:
    error = await registration_service.check_can_apply(session, message.from_user.id)
    if error:
        await message.answer(error)
        return
    await state.clear()
    await state.set_state(RegistrationForm.full_name)
    await message.answer(texts.REG_START)


@router.message(RegistrationForm.full_name, F.text)
async def form_full_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if len(name) < 5 or len(name) > 255 or len(name.split()) < 2:
        await message.answer(texts.REG_NAME_INVALID)
        return
    await state.update_data(full_name=name)
    await state.set_state(RegistrationForm.university_search)
    await message.answer(texts.REG_UNI_PROMPT)


@router.message(RegistrationForm.university_search, F.text)
async def form_university_search(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    query = message.text.strip()
    await state.update_data(university_query=query)
    results = await university_repo.search(session, query)
    text = texts.REG_UNI_CHOOSE if results else texts.REG_UNI_NOT_FOUND
    await message.answer(text, reply_markup=university_results_kb(results))


@router.callback_query(RegistrationForm.university_search, UniversityPickCB.filter())
async def form_university_pick(
    callback: CallbackQuery,
    callback_data: UniversityPickCB,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    university = await university_repo.get(session, callback_data.university_id)
    if university is None:
        await callback.answer(texts.REG_UNI_GONE, show_alert=True)
        return
    await state.update_data(
        university_id=university.university_id,
        university_name=university.canonical_name,
        new_university_name=None,
    )
    await state.set_state(RegistrationForm.university_group)
    await callback.message.edit_text(
        texts.REG_UNI_PICKED.format(university=university.canonical_name)
    )
    await callback.message.answer(texts.REG_GROUP_PROMPT)
    await callback.answer()


@router.callback_query(RegistrationForm.university_search, UniversityNewCB.filter())
async def form_university_new(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(RegistrationForm.university_new_name)
    await callback.message.answer(texts.REG_UNI_NEW_PROMPT)
    await callback.answer()


@router.message(RegistrationForm.university_new_name, F.text)
async def form_university_new_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if len(name) < 5 or len(name) > 255:
        await message.answer(texts.REG_UNI_NEW_TOO_SHORT)
        return
    await state.update_data(university_id=None, university_name=name, new_university_name=name)
    await state.set_state(RegistrationForm.university_group)
    await message.answer(texts.REG_GROUP_PROMPT)


@router.message(RegistrationForm.university_group, F.text)
async def form_university_group(message: Message, state: FSMContext) -> None:
    group = message.text.strip()
    if not group or len(group) > 50:
        await message.answer(texts.REG_GROUP_INVALID)
        return
    await state.update_data(university_group=group)
    await state.set_state(RegistrationForm.birth_date)
    await message.answer(texts.REG_BIRTH_PROMPT)


@router.message(RegistrationForm.birth_date, F.text)
async def form_birth_date(message: Message, state: FSMContext) -> None:
    try:
        birth_date = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
    except ValueError:
        await message.answer(texts.REG_BIRTH_INVALID)
        return
    age = (date.today() - birth_date).days // 365
    if age < 14 or age > 100:
        await message.answer(texts.REG_BIRTH_IMPLAUSIBLE)
        return
    await state.update_data(birth_date=birth_date.isoformat())
    await state.set_state(RegistrationForm.confirm)
    data = await state.get_data()
    summary = texts.REG_SUMMARY.format(
        name=data["full_name"],
        university=data["university_name"],
        group=data["university_group"],
        birth_date=birth_date.strftime("%d.%m.%Y"),
    )
    await message.answer(summary, reply_markup=confirm_kb())


@router.callback_query(RegistrationForm.confirm, RegFormCB.filter())
async def form_confirm(
    callback: CallbackQuery,
    callback_data: RegFormCB,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if callback_data.action == "cancel":
        await state.clear()
        await callback.message.edit_text(texts.REG_CANCELLED)
        await callback.answer()
        return
    if callback_data.action == "restart":
        await state.clear()
        await state.set_state(RegistrationForm.full_name)
        await callback.message.edit_text(texts.REG_RESTARTED)
        await callback.answer()
        return

    error = await registration_service.check_can_apply(session, callback.from_user.id)
    if error:
        await state.clear()
        await callback.message.edit_text(error)
        await callback.answer()
        return
    data = await state.get_data()
    await registration_service.submit_request(session, callback.bot, callback.from_user, data)
    await state.clear()
    await callback.message.edit_text(texts.REG_SUBMITTED)
    await callback.answer()
