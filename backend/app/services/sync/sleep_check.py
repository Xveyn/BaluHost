"""Sleep window overlap check for sync scheduling."""


def is_time_in_sleep_window(sync_time: str, sleep_time: str, wake_time: str) -> bool:
    """Check if sync_time (HH:MM) falls within the sleep window [sleep_time, wake_time).

    Handles overnight windows (e.g. 23:00-06:00).
    Returns False if sleep_time == wake_time (no valid window).
    """
    if sleep_time == wake_time:
        return False

    sync_minutes = _to_minutes(sync_time)
    sleep_minutes = _to_minutes(sleep_time)
    wake_minutes = _to_minutes(wake_time)

    if sleep_minutes < wake_minutes:
        # Normal window: e.g. 14:00-16:00
        return sleep_minutes <= sync_minutes < wake_minutes
    else:
        # Overnight window: e.g. 23:00-06:00
        return sync_minutes >= sleep_minutes or sync_minutes < wake_minutes


def _to_minutes(time_str: str) -> int:
    """Convert HH:MM string to minutes since midnight."""
    h, m = map(int, time_str.split(":"))
    return h * 60 + m
