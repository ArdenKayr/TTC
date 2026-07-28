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
from bot.keyboards.common_kb import main_menu_kb


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
