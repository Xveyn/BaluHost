"""When to speak about the connection, and when to stay quiet.

Both are state over time, which is why they live here as small testable units
rather than as flags scattered through the loop.
"""

from __future__ import annotations

RECONNECT_ANNOUNCE_AFTER = 120.0


class ConnectionAnnouncer:
    """Says "gone" once, and "back" only after a real outage.

    A backend that flaps must not produce a stream of popups. Two mechanisms
    guard against that, for two different kinds of repetition:

    - `_announced` blocks a repeat *within* one continuous offline phase: as
      long as the connection has not been seen up since the last loss
      announcement, further went_offline() calls stay silent.
    - `_last_announced_at` blocks a repeat *across* phases. came_online()
      clears `_announced` on every call, even one that stays silent because
      the outage was too short to announce a return — so a quick flap
      (offline, briefly back, offline again) would otherwise slip past the
      first guard and re-announce within seconds. The reconnect threshold
      doubles as the minimum gap between two loss announcements.
    """

    def __init__(self, reconnect_after: float = RECONNECT_ANNOUNCE_AFTER) -> None:
        self._reconnect_after = reconnect_after
        self._offline_since: float | None = None
        self._announced = False
        self._last_announced_at: float | None = None

    def went_offline(self, now: float) -> tuple[str, str] | None:
        if self._announced:
            return None
        self._offline_since = now
        self._announced = True
        if (
            self._last_announced_at is not None
            and now - self._last_announced_at < self._reconnect_after
        ):
            return None
        self._last_announced_at = now
        return ("BaluHost", "Keine Verbindung zum Backend")

    def came_online(self, now: float) -> tuple[str, str] | None:
        since, self._offline_since = self._offline_since, None
        self._announced = False
        if since is None or now - since < self._reconnect_after:
            return None
        return ("BaluHost", "Verbindung wiederhergestellt")


class QuietMode:
    """Hold popups until a deadline, set from the tray menu."""

    def __init__(self) -> None:
        self._until = 0.0

    def mute_for(self, seconds: float, now: float) -> None:
        self._until = now + seconds

    def clear(self) -> None:
        self._until = 0.0

    def is_muted(self, now: float) -> bool:
        return now < self._until
