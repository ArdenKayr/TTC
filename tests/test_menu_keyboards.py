"""Нижнее меню под ролью человека.

Меню в Telegram живёт, пока его не заменят новым сообщением, поэтому бот
обязан прислать новое меню в тот момент, когда решение админа меняет статус
человека (одобрение заявки, разбан). Здесь проверяется сам состав меню —
что именно должно прийти одобренному участнику вместо «📝 Регистрация».
"""

from datetime import date

from bot import texts
from bot.db.models import User
from bot.enums import PermissionModule, UserRole
from bot.keyboards.common_kb import admin_panel_kb, info_menu_kb, main_menu_kb

_ALL_MODULES = {module.value for module in PermissionModule}


def _user(role: UserRole) -> User:
    return User(
        tg_id=1,
        display_name="Тест",
        birth_date=date(2000, 1, 1),
        current_role=role,
    )


def _labels(keyboard) -> set[str]:
    return {button.text for row in keyboard.keyboard for button in row}


def test_guest_menu_offers_registration():
    assert _labels(main_menu_kb(None)) == {texts.BTN.START_REGISTER, texts.BTN.START_ABOUT}


def test_approved_user_menu_replaces_registration_button():
    """Главное: у одобренного не должно остаться кнопки «Регистрация»."""
    labels = _labels(main_menu_kb(_user(UserRole.USER)))
    assert texts.BTN.START_REGISTER not in labels
    assert labels == {
        texts.BTN.INFO,
        texts.BTN.PROFILE,
        texts.BTN.ACT_NEW,
        texts.BTN.VOTE_NEW,
        texts.BTN.REPORT,
    }


def test_admin_mode_button_for_everyone_with_powers():
    """Кнопку «Админство» видит каждый, у кого есть админские возможности.

    Раньше её показывали только суперадминам, а обычный админ работал
    командами. Команд больше нет, поэтому без этой кнопки он остался бы
    вообще без инструментов.
    """
    for role in (UserRole.USER, UserRole.ORGANIZER):
        assert texts.BTN.ADMIN_MODE not in _labels(main_menu_kb(_user(role)))
    for role in (UserRole.ADMIN, UserRole.SUPERADMIN, UserRole.OWNER):
        assert texts.BTN.ADMIN_MODE in _labels(main_menu_kb(_user(role)))

    personal = _user(UserRole.USER)
    personal.custom_permissions = {"modules": [PermissionModule.CONTENT.value]}
    assert texts.BTN.ADMIN_MODE in _labels(main_menu_kb(personal)), (
        "Человеку выдали личный модуль, а входа в админку не дали."
    )

    grouped = _user(UserRole.USER)
    grouped.permission_group_id = 1
    assert texts.BTN.ADMIN_MODE in _labels(main_menu_kb(grouped)), (
        "Человека добавили в группу прав, а входа в админку не дали."
    )


def test_panel_shows_only_allowed_sections():
    """В панели ровно то, что человеку разрешено, — и ничего сверх."""
    owner = _labels(admin_panel_kb(_user(UserRole.OWNER), _ALL_MODULES))
    for button in (texts.BTN.ADMIN_PANEL_LOGS, texts.BTN.ADMIN_PANEL_UPDATES):
        assert button in owner

    superadmin = _labels(admin_panel_kb(_user(UserRole.SUPERADMIN), _ALL_MODULES))
    assert texts.BTN.ADMIN_PANEL_CRUD in superadmin
    for button in (texts.BTN.ADMIN_PANEL_LOGS, texts.BTN.ADMIN_PANEL_UPDATES):
        assert button not in superadmin, "Разделы владельца не должны утекать суперадмину."

    # Человеку выдали только «тексты»: кроме «Разделов» и выхода — ничего.
    only_content = _labels(
        admin_panel_kb(_user(UserRole.USER), {PermissionModule.CONTENT.value})
    )
    assert only_content == {texts.BTN.ADMIN_PANEL_CONTENT, texts.BTN.ADMIN_PANEL_USER_MODE}


def test_every_former_command_has_its_section():
    """У каждой убранной команды есть кнопка — иначе возможность потеряна.

    2026-08-02 команды /content, /activities, /admins, /ban, /unban, /setrole
    убраны. Всё, что они делали, должно открываться из панели.
    """
    owner = _labels(admin_panel_kb(_user(UserRole.OWNER), _ALL_MODULES))
    for button in (
        texts.BTN.ADMIN_PANEL_CONTENT,  # было /content
        texts.BTN.ADMIN_PANEL_ACTIVITIES,  # было /activities
        texts.BTN.ADMIN_PANEL_PERMS,  # было /admins
        texts.BTN.ADMIN_PANEL_USERS,  # было /ban, /unban, /setrole
    ):
        assert button in owner, f"Команду убрали, а кнопку «{button}» не дали."
    assert texts.BTN.ADMIN_PANEL_USER_MODE in owner, "Из панели должен быть выход."


def test_moderator_reaches_users_section():
    """Модуль «Бан и разбан» без раздела «Пользователи» бесполезен."""
    labels = _labels(
        admin_panel_kb(_user(UserRole.USER), {PermissionModule.MODERATION.value})
    )
    assert texts.BTN.ADMIN_PANEL_USERS in labels


def test_guide_button_is_in_the_info_menu():
    """«Инструкция» — первое, что ищет человек, не понявший бота."""
    for is_super in (True, False):
        assert texts.BTN.INFO_GUIDE in _labels(info_menu_kb(is_super))
    assert texts.BTN.INFO_ADMIN_REGS in _labels(info_menu_kb(True))
    assert texts.BTN.INFO_ADMIN_REGS not in _labels(info_menu_kb(False))
