"""Нижнее меню под ролью человека.

Меню в Telegram живёт, пока его не заменят новым сообщением, поэтому бот
обязан прислать новое меню в тот момент, когда решение админа меняет статус
человека (одобрение заявки, разбан). Здесь проверяется сам состав меню —
что именно должно прийти одобренному участнику вместо «📝 Регистрация».
"""

from datetime import date

from bot import texts
from bot.db.models import User
from bot.enums import UserRole
from bot.keyboards.common_kb import admin_panel_kb, info_menu_kb, main_menu_kb


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


def test_admin_mode_button_only_for_superadmin_and_owner():
    for role in (UserRole.USER, UserRole.ORGANIZER, UserRole.ADMIN):
        assert texts.BTN.ADMIN_MODE not in _labels(main_menu_kb(_user(role)))
    for role in (UserRole.SUPERADMIN, UserRole.OWNER):
        assert texts.BTN.ADMIN_MODE in _labels(main_menu_kb(_user(role)))


def test_content_editor_is_reachable_from_the_panel():
    """Редактор страниц должен открываться кнопкой, а не только командой.

    Так и было до 2026-08-02: страницы раздела «Информация» правились лишь
    командой /content, которой не было ни в одном меню. Владелец искал их в
    «Сценариях» — там их нет и быть не может (это другой редактор) — и сделал
    вывод, что возможности просто не существует.
    """
    for is_owner in (True, False):
        labels = _labels(admin_panel_kb(is_owner))
        assert texts.BTN.ADMIN_PANEL_CONTENT in labels, (
            "В панели «Админство» нет кнопки редактора страниц — найти его "
            "снова можно будет только по памяти."
        )
        assert texts.BTN.ADMIN_PANEL_SCENARIOS in labels
        assert texts.BTN.ADMIN_PANEL_USER_MODE in labels, "Из панели должен быть выход."


def test_owner_only_buttons_in_the_panel():
    owner = _labels(admin_panel_kb(True))
    superadmin = _labels(admin_panel_kb(False))
    for button in (texts.BTN.ADMIN_PANEL_LOGS, texts.BTN.ADMIN_PANEL_UPDATES):
        assert button in owner
        assert button not in superadmin


def test_guide_button_is_in_the_info_menu():
    """«Инструкция» — первое, что ищет человек, не понявший бота."""
    for is_super in (True, False):
        assert texts.BTN.INFO_GUIDE in _labels(info_menu_kb(is_super))
    assert texts.BTN.INFO_ADMIN_REGS in _labels(info_menu_kb(True))
    assert texts.BTN.INFO_ADMIN_REGS not in _labels(info_menu_kb(False))
