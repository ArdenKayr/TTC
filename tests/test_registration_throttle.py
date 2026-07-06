import pytest

from bot.services.throttle import TIMEOUT_CAP_MINUTES, rejection_timeout_minutes


@pytest.mark.parametrize(
    ("attempt_number", "expected_minutes"),
    [
        (1, 0),
        (2, 10),
        (3, 30),
        (4, 70),
        (5, 150),
        (6, 310),
    ],
)
def test_matches_spec_sequence(attempt_number: int, expected_minutes: int) -> None:
    assert rejection_timeout_minutes(attempt_number) == expected_minutes


def test_capped_for_persistent_abusers() -> None:
    assert rejection_timeout_minutes(20) == TIMEOUT_CAP_MINUTES
    assert rejection_timeout_minutes(100) == TIMEOUT_CAP_MINUTES


def test_monotonic_until_cap() -> None:
    values = [rejection_timeout_minutes(n) for n in range(1, 15)]
    assert values == sorted(values)
