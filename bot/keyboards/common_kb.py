from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from bot import texts
from bot.db.models import User
from bot.enums import FULL_ADMIN_ROLES, PermissionModule, UserRole
from bot.keyboards.callback_data import AdminCallCB

_SUPER_ROLES = (UserRole.SUPERADMIN, UserRole.OWNER)

# Тексты всех реплай-кнопок меню: FSM-формы игнорируют их как «значение»
# (нажатие кнопки меню посреди ввода отменяет форму, а не сохраняется).
MENU_BUTTON_TEXTS = {
    texts.BTN.INFO,
    texts.BTN.PROFILE,
    texts.BTN.REPORT,
    texts.BTN.ACT_NEW,
    texts.BTN.VOTE_NEW,
    texts.BTN.ADMIN_MODE,
    texts.BTN.ADMIN_PANEL_USERS,
    texts.BTN.ADMIN_PANEL_CRUD,
    texts.BTN.ADMIN_PANEL_SCENARIOS,
    texts.BTN.ADMIN_PANEL_CONTENT,
    texts.BTN.ADMIN_PANEL_PERMS,
    texts.BTN.ADMIN_PANEL_ACTIVITIES,
    texts.BTN.ADMIN_PANEL_LOGS,
    texts.BTN.ADMIN_PANEL_UPDATES,
    texts.BTN.ADMIN_PANEL_USER_MODE,
}


def has_admin_powers(user: User) -> bool:
    """Есть ли у человека хоть что-то админское — видно по самой записи.

    Проверка нарочно не ходит в базу: главное меню собирается в доброй дюжине
    мест, и все они синхронные. Роль, назначенная группа прав и личные модули
    лежат прямо в записи пользователя, а их достаточно, чтобы решить, показывать
    ли кнопку «Админство». Точный состав разделов внутри панели считается уже с
    базой — там это одно обращение на нажатие.
    """
    if user.current_role in FULL_ADMIN_ROLES:
        return True
    if user.permission_group_id is not None:
        return True
    return bool((user.custom_permissions or {}).get("modules"))


def admin_sections(user: User, modules: set[str]) -> list[str]:
    """Разделы панели «Админство», доступные этому человеку.

    До 2026-08-02 половина этих разделов открывалась только командами
    (/content, /activities, /ban, /unban, /admins), а панель видели лишь
    суперадмины — обычный админ со своими модулями не имел ни одной кнопки.
    Теперь список собирается по правам: что человеку разрешено, то он и видит.
    """
    is_owner = user.current_role == UserRole.OWNER
    is_super = user.current_role in _SUPER_ROLES
    is_full_admin = user.current_role in FULL_ADMIN_ROLES

    sections: list[str] = []
    # Карточка человека: роли — суперадминам, бан и разбан — по модулю.
    if is_super or PermissionModule.MODERATION.value in modules:
        sections.append(texts.BTN.ADMIN_PANEL_USERS)
    if PermissionModule.ACTIVITIES.value in modules:
        sections.append(texts.BTN.ADMIN_PANEL_ACTIVITIES)
    if PermissionModule.CONTENT.value in modules:
        sections.append(texts.BTN.ADMIN_PANEL_CONTENT)
    if is_full_admin:
        sections.append(texts.BTN.ADMIN_PANEL_PERMS)
    if is_super:
        sections.append(texts.BTN.ADMIN_PANEL_CRUD)
        sections.append(texts.BTN.ADMIN_PANEL_SCENARIOS)
    if is_owner:
        sections.append(texts.BTN.ADMIN_PANEL_LOGS)
        sections.append(texts.BTN.ADMIN_PANEL_UPDATES)
    return sections


def _reply(rows: list[list[KeyboardButton]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выберите действие в меню",
    )


def main_menu_kb(user: User | None) -> ReplyKeyboardMarkup:
    """Постоянное меню внизу экрана (главный экран бота)."""
    if user is None:
        return _reply(
            [
                [KeyboardButton(text=texts.BTN.START_REGISTER)],
                [KeyboardButton(text=texts.BTN.START_ABOUT)],
            ]
        )
    # Компактно: по две кнопки в ряд, всё меню видно без пролистывания.
    third_row = [KeyboardButton(text=texts.BTN.REPORT)]
    if has_admin_powers(user):
        third_row.append(KeyboardButton(text=texts.BTN.ADMIN_MODE))
    return _reply(
        [
            [KeyboardButton(text=texts.BTN.INFO), KeyboardButton(text=texts.BTN.PROFILE)],
            [KeyboardButton(text=texts.BTN.ACT_NEW), KeyboardButton(text=texts.BTN.VOTE_NEW)],
            third_row,
        ]
    )


def info_menu_kb(is_superadmin: bool) -> ReplyKeyboardMarkup:
    """Подменю «Информация»: каждая кнопка — редактируемый блок контента."""
    last_row = [KeyboardButton(text=texts.BTN.BACK_TO_MENU)]
    if is_superadmin:
        last_row.insert(0, KeyboardButton(text=texts.BTN.INFO_ADMIN_REGS))
    return _reply(
        [
            # Инструкция — во всю ширину и первой строкой: это то, с чего человеку
            # проще всего начать, когда он не понимает, что вообще умеет бот.
            [KeyboardButton(text=texts.BTN.INFO_GUIDE)],
            [KeyboardButton(text=texts.BTN.START_ABOUT), KeyboardButton(text=texts.BTN.INFO_RULES)],
            [KeyboardButton(text=texts.BTN.INFO_DOCS), KeyboardButton(text=texts.BTN.INFO_UPDATES)],
            [
                KeyboardButton(text=texts.BTN.INFO_BECOME_ORG),
                KeyboardButton(text=texts.BTN.INFO_BECOME_ADMIN),
            ],
            last_row,
        ]
    )


def admin_panel_kb(user: User, modules: set[str]) -> ReplyKeyboardMarkup:
    """Меню режима «Админство»: только разрешённые разделы, по два в ряд."""
    sections = admin_sections(user, modules)
    rows = [
        [KeyboardButton(text=label) for label in sections[i : i + 2]]
        for i in range(0, len(sections), 2)
    ]
    rows.append([KeyboardButton(text=texts.BTN.ADMIN_PANEL_USER_MODE)])
    return _reply(rows)


def admin_call_kb() -> InlineKeyboardMarkup:
    """«Возьмусь» под вызовом админов — чтобы на один вызов не бежали все сразу."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.BTN.CALL_CLAIM, callback_data=AdminCallCB().pack())]
        ]
    )
