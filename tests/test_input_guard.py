"""Бот не молчит: на любое сообщение есть ответ.

Раньше шаг анкеты ждал текст, а человек присылал фото — и не срабатывал ни
один обработчик. Со стороны это неотличимо от поломки: сообщение ушло,
ответа нет, непонятно, ждать или начинать заново. Теперь у каждого ожидания
есть «последний рубеж» — обработчик без фильтров, который объясняет, что
именно не подошло, и повторяет вопрос.

Здесь проверяется и сама формулировка ответа, и то, что рубеж стоит на месте:
ловушка, уехавшая выше шагов, перехватила бы анкету целиком — и молча.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from bot import texts
from bot.services import input_guard

ROOT = Path(__file__).resolve().parent.parent


class _Msg:
    """Сообщение с одним заполненным полем — такими их и присылает Telegram."""

    def __init__(self, **fields) -> None:
        self.text = None
        self.__dict__.update(fields)


# --- Что человек прислал ---


@pytest.mark.parametrize(
    "field, expected",
    [
        ("photo", "фото"),
        ("voice", "голосовое сообщение"),
        ("sticker", "стикер"),
        ("document", "файл"),
        ("video_note", "кружок"),
        ("location", "геопозицию"),
    ],
)
def test_attachment_is_named_the_way_people_call_it(field, expected):
    assert input_guard.kind(_Msg(**{field: object()})) == expected


def test_unknown_attachment_does_not_break_the_answer():
    """Telegram добавляет новые виды сообщений — бот не должен на них падать."""
    assert input_guard.kind(_Msg(game=object())) == texts.INPUT_KIND_UNKNOWN


def test_every_known_kind_has_a_human_name():
    """Сторож: вид, известный коду, но забытый в текстах, уронил бы ответ.

    Падало бы это в тот момент, когда человек прислал именно такое сообщение,
    то есть на живом человеке и не сразу.
    """
    for field in input_guard._KINDS:
        assert field in texts.INPUT_KINDS, f"вид «{field}» не назван в texts.INPUT_KINDS"


def test_caption_does_not_turn_a_photo_into_text():
    """Фото с подписью — это фото: подпись не делает его текстовым ответом."""
    assert input_guard.kind(_Msg(photo=object(), caption="держи")) == "фото"


# --- Что бот отвечает ---


def test_form_says_it_is_alive_and_what_it_expects():
    answer = input_guard.form_explain(_Msg(photo=object()))
    assert "Бот работает" in answer
    assert "фото" in answer


def test_form_step_with_files_does_not_claim_it_wants_text_only():
    """Редактор разделов принимает и картинки — врать про «только текст» нельзя."""
    answer = input_guard.form_explain(_Msg(sticker=object()), files_ok=True)
    assert answer == texts.FORM_INPUT_WITH_FILES.format(kind="стикер")


def test_command_gets_its_own_answer():
    """Команд у бота нет, но их пробуют по привычке — молчать особенно обидно."""
    assert input_guard.form_explain(_Msg(text="/activities")) == texts.FORM_INPUT_COMMAND
    assert input_guard.menu_explain(_Msg(text="/admin")) == texts.MENU_INPUT_COMMAND


def test_text_where_a_button_is_expected():
    """Текст дошёл, но шаг выбирается кнопкой — это не «пришло не то вложение»."""
    assert input_guard.form_explain(_Msg(text="ага")) == texts.FORM_INPUT_NEEDS_BUTTON


def test_menu_answer_points_at_the_buttons():
    assert "меню внизу" in input_guard.menu_explain(_Msg(text="привет"))
    assert "стикер" in input_guard.menu_explain(_Msg(sticker=object()))


# --- Сторожа: рубеж стоит на месте ---


def _message_filters(path: Path) -> list[str]:
    """Фильтры обработчиков сообщений роутера — по порядку регистрации.

    Порядок и есть поведение: aiogram отдаёт сообщение первому подошедшему.
    """
    source = path.read_text(encoding="utf-8")
    return [chunk.split("async def")[0] for chunk in source.split("@router.message(")[1:]]


def _is_catcher(filters: str, markers: tuple[str, ...]) -> bool:
    """Ловушка — обработчик состояния без разбора содержимого сообщения.

    «F.» или «Command» в фильтре означают, что обработчик берёт только часть
    сообщений, а значит остальные снова уходят в молчание.
    """
    if not any(marker in filters for marker in markers):
        return False
    return "F." not in filters and "Command" not in filters


# Форма — файл, где живут её шаги, и то, чем в этом файле обозначена ловушка.
FORMS = [
    ("RegistrationForm", "bot/routers/registration.py", ("RegistrationForm",)),
    ("ActivityForm", "bot/routers/activities.py", ("ActivityForm", "_ANY_FORM")),
    ("VoteForm", "bot/routers/activities.py", ("VoteForm", "_ANY_FORM")),
    ("ProfileForm", "bot/routers/profile.py", ("ProfileForm",)),
    ("ReportForm", "bot/routers/user_menu.py", ("ReportForm",)),
    ("SuperadminForm", "bot/routers/superadmin.py", ("SuperadminForm",)),
    ("CrudForm", "bot/routers/admin/crud_admin.py", ("CrudForm",)),
    ("ContentEditForm", "bot/routers/admin/content_admin.py", ("ContentEditForm",)),
    ("ScenarioEditForm", "bot/routers/admin/scenario_admin.py", ("ScenarioEditForm",)),
    ("UpdatePostForm", "bot/routers/admin/owner_panel.py", ("UpdatePostForm",)),
    ("PermAdminForm", "bot/routers/admin/permissions_admin.py", ("PermAdminForm",)),
    ("ReviewEditForm", "bot/routers/admin/university_review.py", ("ReviewEditForm",)),
]


@pytest.mark.parametrize("form, router, markers", FORMS)
def test_every_form_answers_anything_at_all(form, router, markers):
    """У каждой формы есть обработчик, который берёт любое сообщение."""
    filters = _message_filters(ROOT / router)
    assert any(_is_catcher(f, markers) for f in filters), (
        f"у формы {form} ({router}) нет последнего рубежа: сообщение, не подошедшее "
        "ни одному шагу, останется без ответа"
    )


@pytest.mark.parametrize("form, router, markers", FORMS)
def test_the_catcher_stands_behind_the_steps(form, router, markers):
    """Ловушка — после шагов, иначе она перехватит саму анкету.

    Это не мелочь порядка: обработчик без фильтров, поднятый выше шагов,
    съест все ответы человека, и анкета перестанет заполняться совсем.
    """
    filters = _message_filters(ROOT / router)
    catcher = max(i for i, f in enumerate(filters) if _is_catcher(f, markers))
    later = [f for f in filters[catcher + 1 :] if any(m in f for m in markers)]
    assert not later, (
        f"в {router} после ловушки {form} остались обработчики её шагов — "
        "до них сообщение уже не дойдёт"
    )


def test_the_bot_has_the_very_last_word_in_private():
    """Общий рубеж бота: последний обработчик последнего роутера.

    Сюда попадает всё, что не разобрал никто: «привет», стикер, старая команда.
    """
    filters = _message_filters(ROOT / "bot/routers/common.py")
    last = filters[-1]
    assert "ChatType.PRIVATE" in last, "общий рубеж должен ловить сообщения в личке"
    assert "SERVICE_MESSAGE" in last, (
        "служебные сообщения (закреп, смена фото) — не повод отвечать человеку"
    )


def test_the_last_word_is_private_only():
    """В группах бот отвечает не на всё подряд — там свой сторож и свои правила."""
    source = (ROOT / "bot/routers/common.py").read_text(encoding="utf-8")
    catcher = source.split("@router.message(")[-1]
    assert "GROUP" not in catcher


def test_menu_and_form_answers_never_lose_their_placeholders():
    """Сторож на тексты: забытая подстановка вылезет к человеку как «{kind}»."""
    for name in ("FORM_INPUT_ONLY_TEXT", "FORM_INPUT_WITH_FILES", "MENU_INPUT_UNKNOWN"):
        template = getattr(texts, name)
        assert "{kind}" in template, f"в {name} потерялась подстановка вида сообщения"
        assert not re.search(r"\{(?!kind\})", template), (
            f"в {name} есть подстановка, которую никто не заполняет"
        )
