"""Массовый сбой не должен добивать бота уведомлениями о самом себе.

Найдено при расчёте нагрузки на тысячу человек 09.09.2026. Каждая ошибка
присылает владельцу карточку в личку. На наплыве регистраций ошибка бывает
не одна, а по одной на каждую заявку: хватит недоступного админ-чата, чтобы
сотня заявок принесла сотню одинаковых карточек. Личка владельца при этом
упирается в собственный лимит Telegram — и бот тратит остатки связи на
рассказ о том, что у него плохо со связью.

Поэтому одинаковые беды показываются раз в десять минут, а пропущенные
пересчитываются и называются числом в следующей карточке. В журнал
«📜 Логи» при этом попадают все до единой: глушится показ, а не запись.
"""

from __future__ import annotations

import pytest

from bot.services import error_service

WINDOW = error_service.DM_WINDOW.total_seconds()


@pytest.fixture(autouse=True)
def _clean_state():
    """Глушитель живёт в памяти процесса — между тестами его надо обнулять."""
    error_service._last_dm.clear()
    yield
    error_service._last_dm.clear()


def test_first_trouble_is_always_shown() -> None:
    """Первая ошибка доходит до владельца немедленно — ради этого всё и есть."""
    assert error_service.should_dm("сбой", 0.0) == (True, 0)


def test_the_same_trouble_is_not_repeated() -> None:
    """Сто одинаковых ошибок подряд — одна карточка, а не сто."""
    error_service.should_dm("сбой", 0.0)
    shown = [error_service.should_dm("сбой", float(i))[0] for i in range(1, 101)]
    assert not any(shown), "После первой карточки одинаковые беды показывать нельзя."


def test_skipped_are_counted_and_named_later() -> None:
    """Пропущенное не теряется: следующая карточка называет, сколько их было."""
    error_service.should_dm("сбой", 0.0)
    for i in range(1, 41):
        error_service.should_dm("сбой", float(i))
    show, skipped = error_service.should_dm("сбой", WINDOW + 1)
    assert show is True, "Через десять минут о беде надо напомнить."
    assert skipped == 40, "Владелец должен узнать, сколько повторов он не видел."


def test_counter_resets_after_it_was_told() -> None:
    """Названное число не называется второй раз."""
    error_service.should_dm("сбой", 0.0)
    error_service.should_dm("сбой", 1.0)
    error_service.should_dm("сбой", WINDOW + 1)  # здесь пропущенные названы
    show, skipped = error_service.should_dm("сбой", 2 * WINDOW + 2)
    assert (show, skipped) == (True, 0)


def test_different_troubles_do_not_silence_each_other() -> None:
    """Глушится повтор одной беды, а не всё подряд: новая беда важнее."""
    error_service.should_dm("сеть", 0.0)
    assert error_service.should_dm("права", 1.0)[0] is True, (
        "Иначе первая же частая ошибка спрячет все остальные."
    )


def test_changing_numbers_do_not_make_a_new_trouble() -> None:
    """Одна и та же беда с разными числами в тексте — всё ещё одна беда.

    Ровно этот случай и надо глушить: при флуде Telegram отвечает «подожди
    столько-то секунд», и число в каждом ответе своё. Считая их разными
    бедами, бот прислал бы карточку на каждую.
    """
    first = error_service._same_trouble("TelegramRetryAfter", "Too Many Requests: retry after 30")
    second = error_service._same_trouble("TelegramRetryAfter", "Too Many Requests: retry after 25")
    assert first == second


def test_different_troubles_of_one_type_stay_apart() -> None:
    """А вот разные по сути беды одного типа склеивать нельзя."""
    assert error_service._same_trouble("TelegramBadRequest", "chat not found") != (
        error_service._same_trouble("TelegramBadRequest", "not enough rights")
    )


def test_different_exception_types_stay_apart() -> None:
    """Разные типы ошибок не склеиваются, даже если текст похож."""
    assert error_service._same_trouble("TelegramNetworkError", "timeout") != (
        error_service._same_trouble("TelegramBadRequest", "timeout")
    )
