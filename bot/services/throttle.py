TIMEOUT_CAP_MINUTES = 4320  # 72 hours


def rejection_timeout_minutes(attempt_number: int) -> int:
    """Penalty after rejecting attempt N: 0, 10, 30, 70, 150... (T_n = 10*(2^(n-1)-1))."""
    return min(10 * (2 ** (attempt_number - 1) - 1), TIMEOUT_CAP_MINUTES)
