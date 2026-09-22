"""Ссылки-приглашения: за что засчитывается человек, а за что — нет.

Счётчик, которому нельзя верить, хуже отсутствия счётчика: по нему будут
решать, кто из админов работает. Поэтому здесь проверяется ровно то, чем такой
счётчик обычно врёт, — повторные заходы, перебивание чужой ссылки своей,
собственные переходы владельца ссылки и мусор в хвосте команды.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.dialects import postgresql

from bot import texts
from bot.db.repositories import referral_repo
from bot.enums import PermissionModule, UserRole
from bot.keyboards.common_kb import MENU_BUTTON_TEXTS, admin_sections
from bot.services import referral_service

GUEST = 500100
ADMIN = 1419203590
OTHER_ADMIN = 777001


class _Link:
    def __init__(self, code: str, owner_tg_id: int, title: str = "Физфак") -> None:
        self.code = code
        self.owner_tg_id = owner_tg_id
        self.title = title


class _Session:
    """Сессия-заглушка: считает коммиты и запоминает выполненные запросы."""

    def __init__(self) -> None:
        self.commits = 0
        self.statements: list = []

    async def commit(self) -> None:
        self.commits += 1

    async def execute(self, statement):
        self.statements.append(statement)


class _Me:
    username = "istinnyi_kurs_bot"


class _Bot:
    async def me(self):
        return _Me()


class _User:
    def __init__(self, tg_id: int, role: UserRole) -> None:
        self.tg_id = tg_id
        self.current_role = role


@pytest.fixture
def store(monkeypatch):
    """Подставной справочник ссылок и переходов — вместо базы."""
    state = {
        "links": {"aaa1111": _Link("aaa1111", ADMIN), "bbb2222": _Link("bbb2222", OTHER_ADMIN)},
        "visits": {},
        "lookups": 0,
    }

    async def get_link(session, code):
        state["lookups"] += 1
        return state["links"].get(code)

    async def add_visit(session, *, code, tg_id):
        if tg_id in state["visits"]:
            return None
        state["visits"][tg_id] = code
        return object()

    monkeypatch.setattr(referral_repo, "get_link", get_link)
    monkeypatch.setattr(referral_repo, "add_visit", add_visit)
    return state


def _start(store, payload: str, *, tg_id: int = GUEST, registered: bool = False):
    return asyncio.run(
        referral_service.note_start(
            _Session(), tg_id=tg_id, payload=payload, is_registered=registered
        )
    )


# --- Кого ссылка засчитывает ---


def test_guest_is_counted(store) -> None:
    assert _start(store, "aaa1111") is not None
    assert store["visits"] == {GUEST: "aaa1111"}


def test_second_visit_changes_nothing(store) -> None:
    """Человек открыл ту же ссылку ещё раз — это не второй приведённый."""
    _start(store, "aaa1111")
    assert _start(store, "aaa1111") is None
    assert store["visits"] == {GUEST: "aaa1111"}


def test_first_link_wins(store) -> None:
    """Чужая ссылка, открытая следом, не перебивает того, кто привёл первым."""
    _start(store, "aaa1111")
    assert _start(store, "bbb2222") is None
    assert store["visits"][GUEST] == "aaa1111", (
        "Иначе приведённого забирал бы тот, кто скинул ссылку последним."
    )


def test_registered_person_is_not_counted(store) -> None:
    """Участника приводить некуда: он давно в сообществе."""
    assert _start(store, "aaa1111", registered=True) is None
    assert store["visits"] == {}


def test_owner_does_not_count_himself(store) -> None:
    """Админ открывает свою ссылку, чтобы проверить, — это не приведённый человек."""
    assert _start(store, "aaa1111", tg_id=ADMIN) is None
    assert store["visits"] == {}


def test_unknown_code_is_ignored(store) -> None:
    assert _start(store, "zzz9999") is None
    assert store["visits"] == {}


@pytest.mark.parametrize("payload", ["", "   ", "код с пробелом", "a" * 65, "<script>"])
def test_garbage_never_reaches_the_database(store, payload: str) -> None:
    """Хвост команды приходит снаружи: за мусором в базу ходить незачем."""
    assert _start(store, payload) is None
    assert store["lookups"] == 0


# --- Сам код ссылки ---


def test_code_is_readable_and_valid() -> None:
    """Код диктуют голосом: ни нуля с «о», ни единицы с «l», ни заглавных."""
    for _ in range(200):
        code = referral_service.new_code()
        assert referral_service.PAYLOAD_RE.match(code)
        assert len(code) == referral_service.CODE_LENGTH
        assert not set(code) & set("0o1lIiO")


def test_unique_code_skips_taken_one(monkeypatch) -> None:
    """Код, который уже занят, не выдаётся: он считал бы переходы не тому."""
    taken = "aaa1111"
    codes = iter([taken, "ccc3333"])
    monkeypatch.setattr(referral_service, "new_code", lambda: next(codes))

    async def get_link(session, code):
        return _Link(taken, ADMIN) if code == taken else None

    monkeypatch.setattr(referral_repo, "get_link", get_link)
    assert asyncio.run(referral_service.unique_code(_Session())) == "ccc3333"


def test_link_url_is_a_normal_bot_link() -> None:
    url = asyncio.run(referral_service.link_url(_Bot(), "aaa1111"))
    assert url == "https://t.me/istinnyi_kurs_bot?start=aaa1111"


# --- Карточка со счётчиками ---


def _render(monkeypatch, links, counters, *, with_owner: bool):
    async def stats(session, codes):
        return {code: counters.get(code, (0, 0, 0)) for code in codes}

    async def label_map(session, tg_ids):
        return {ADMIN: "Арден"}

    monkeypatch.setattr(referral_repo, "stats", stats)
    monkeypatch.setattr(referral_service.user_repo, "label_map", label_map)
    return asyncio.run(
        referral_service.render_links(_Session(), _Bot(), links, with_owner=with_owner)
    )


def test_card_shows_three_numbers(monkeypatch) -> None:
    cards = _render(
        monkeypatch,
        [_Link("aaa1111", ADMIN)],
        {"aaa1111": (42, 18, 15)},
        with_owner=False,
    )
    card = cards[0][1]
    assert "42" in card and "18" in card and "15" in card
    assert "https://t.me/istinnyi_kurs_bot?start=aaa1111" in card


def test_fresh_link_shows_zeroes(monkeypatch) -> None:
    """По новой ссылке ещё никто не пришёл — это нули, а не пустое место."""
    card = _render(monkeypatch, [_Link("aaa1111", ADMIN)], {}, with_owner=False)[0][1]
    assert card.count("0") >= 3


def test_owner_is_named_only_when_asked(monkeypatch) -> None:
    """Суперадмин видит чужие ссылки — без имени они неотличимы."""
    with_owner = _render(monkeypatch, [_Link("aaa1111", ADMIN)], {}, with_owner=True)[0][1]
    assert "Арден" in with_owner
    plain = _render(monkeypatch, [_Link("aaa1111", ADMIN)], {}, with_owner=False)[0][1]
    assert "Арден" not in plain


def test_link_outlives_its_owner(monkeypatch) -> None:
    """Админ удалил аккаунт — сколько он привёл, из истории не вычёркивается."""
    card = _render(
        monkeypatch, [_Link("aaa1111", None)], {"aaa1111": (9, 4, 3)}, with_owner=True
    )[0][1]
    assert "9" in card and "аккаунт удалён" in card


def test_title_is_escaped(monkeypatch) -> None:
    """Название придумывает человек, а карточка уходит в Telegram разметкой."""
    card = _render(
        monkeypatch, [_Link("aaa1111", ADMIN, "<b>Физфак</b>")], {}, with_owner=False
    )[0][1]
    assert "&lt;b&gt;Физфак&lt;/b&gt;" in card


# --- Отметки вех ---


def _sql(statement) -> str:
    return str(
        statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )


def test_milestones_are_marked_once() -> None:
    """Повторная анкета после отказа не удваивает «дошёл до анкеты»."""
    session = _Session()
    asyncio.run(referral_service.note_applied(session, GUEST))
    asyncio.run(referral_service.note_approved(session, GUEST))
    applied, approved = (_sql(s) for s in session.statements)
    assert "applied_at IS NULL" in applied
    assert "approved_at IS NULL" in approved


# --- Кто видит раздел ---


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.SUPERADMIN, UserRole.OWNER])
def test_full_admin_has_the_section(role: UserRole) -> None:
    sections = admin_sections(_User(ADMIN, role), {m.value for m in PermissionModule})
    assert texts.BTN.ADMIN_PANEL_REFERRALS in sections


def test_single_module_helper_has_no_section() -> None:
    """Раздел — не участок работы, а счётчик того, кто отвечает за набор."""
    sections = admin_sections(
        _User(GUEST, UserRole.USER), {PermissionModule.CONTENT.value}
    )
    assert texts.BTN.ADMIN_PANEL_REFERRALS not in sections


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        (UserRole.ADMIN, False),
        (UserRole.SUPERADMIN, True),
        (UserRole.OWNER, True),
    ],
)
def test_who_sees_other_peoples_links(role: UserRole, expected: bool) -> None:
    assert referral_service.may_see_all(_User(ADMIN, role)) is expected


# --- Кто может убрать ссылку ---


def test_owner_deletes_his_own_link() -> None:
    """Своя ссылка убирается по желанию — без разработчика и без владельца."""
    link = _Link("aaa1111", ADMIN)
    assert referral_service.may_delete(_User(ADMIN, UserRole.ADMIN), link) is True


def test_neighbour_admin_cannot_delete() -> None:
    """Удаление уносит счётчики: чужую работу стирать не соседу с теми же правами."""
    link = _Link("aaa1111", ADMIN)
    assert referral_service.may_delete(_User(OTHER_ADMIN, UserRole.ADMIN), link) is False


@pytest.mark.parametrize("role", [UserRole.SUPERADMIN, UserRole.OWNER])
def test_superadmin_deletes_any_link(role: UserRole) -> None:
    link = _Link("aaa1111", ADMIN)
    assert referral_service.may_delete(_User(OTHER_ADMIN, role), link) is True


@pytest.mark.parametrize(
    ("role", "expected"),
    [(UserRole.ADMIN, False), (UserRole.SUPERADMIN, True), (UserRole.OWNER, True)],
)
def test_ownerless_link_is_cleaned_up_from_above(role: UserRole, expected: bool) -> None:
    """Хозяин удалил аккаунт — убрать его ссылку может только тот, кто выше."""
    link = _Link("aaa1111", None)
    assert referral_service.may_delete(_User(ADMIN, role), link) is expected


def test_section_button_leaves_the_form() -> None:
    """Нажатие раздела посреди ввода — выход, а не название ссылки."""
    assert texts.BTN.ADMIN_PANEL_REFERRALS in MENU_BUTTON_TEXTS
