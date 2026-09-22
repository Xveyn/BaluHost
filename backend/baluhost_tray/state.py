"""Tray state: which notifications are unread, and what colour that makes.

No Qt in here on purpose. tray.py stays thin so everything worth testing is
testable without a display, a bus or a panel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class IconState(str, Enum):
    OFFLINE = "offline"
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class TrayState:
    """Unread notifications by id, plus why the icon is grey.

    Grey has two causes and they need different reactions from the user:
    the backend is unreachable (wait), or the pairing is gone (re-pair). The
    desktop notification that says so disappears after a few seconds; the
    tooltip is the only lasting explanation, so it has to tell them apart.
    """

    connected: bool = False
    paired: bool = True
    unread: dict[int, str] = field(default_factory=dict)

    def set_connected(self, connected: bool) -> None:
        self.connected = connected

    def set_paired(self, paired: bool) -> None:
        """Remember that the device was revoked.

        One way only in practice: nothing re-pairs at runtime, that needs
        `baluhost-tray --pair` and a restart of the service.
        """
        self.paired = paired

    def apply_snapshot(self, items: list[tuple[int, str]]) -> None:
        """Replace the whole set. The REST snapshot is the truth, not a merge.

        This is also how a snoozed notification comes back: the server hides
        it while the snooze runs and returns it afterwards, and nothing else
        would ever re-colour the icon.
        """
        self.unread = {nid: ntype for nid, ntype in items}

    def add(self, notification_id: int, notification_type: str) -> None:
        self.unread[notification_id] = notification_type

    def remove(self, ids: list[int]) -> None:
        for nid in ids:
            self.unread.pop(nid, None)

    def unread_count(self) -> int:
        return len(self.unread)

    def icon_state(self) -> IconState:
        """Worst unread severity wins; no connection beats everything.

        An unknown type counts as harmless: a new NotificationType in the
        backend must not make the panel guess red.

        Unpaired is grey too — the same colour as unreachable, on purpose.
        Only the tooltip separates the two; a fifth icon state would say
        nothing a colour can carry. The explicit `not self.paired` keeps that
        true even if a caller ever forgets the matching set_connected(False).
        """
        if not self.connected or not self.paired:
            return IconState.OFFLINE
        types = set(self.unread.values())
        if "critical" in types:
            return IconState.CRITICAL
        if "warning" in types:
            return IconState.WARNING
        return IconState.OK

    def tooltip(self) -> str:
        """What the icon actually knows — no health promise.

        Green means "nothing unread", not "the box is healthy": reading a
        notification clears the colour while the degraded array stays
        degraded. Saying so here keeps the icon honest.

        Grey says which kind of grey it is. "Nicht erreichbar" means wait;
        "nicht gekoppelt" means act, and names the command that does it —
        the popup that said so is long gone by the time anyone hovers.
        """
        if not self.paired:
            return "BaluHost — nicht gekoppelt: baluhost-tray --pair"
        if not self.connected:
            return "BaluHost — nicht erreichbar"
        count = self.unread_count()
        if not count:
            return "BaluHost — nichts Ungelesenes"
        if count == 1:
            return "BaluHost — 1 ungelesene Meldung"
        return f"BaluHost — {count} ungelesene Meldungen"


SUMMARY_THRESHOLD = 4


@dataclass(frozen=True)
class PendingPopup:
    notification_id: int
    title: str
    message: str


class PopupQueue:
    """Popups held back while a game is on screen or quiet mode runs.

    Held, not dropped: when the reason goes away the user still gets told. A
    reconnect may replay the same notification, so entries are keyed by id.
    """

    def __init__(self) -> None:
        self._held: dict[int, PendingPopup] = {}

    def hold(self, popup: PendingPopup) -> None:
        self._held.setdefault(popup.notification_id, popup)

    def is_empty(self) -> bool:
        return not self._held

    def release(self) -> tuple[list[PendingPopup], tuple[str, str] | None]:
        """Return everything held plus the summary, and forget it.

        Summary and content come back together on purpose: computing the
        summary after clearing would always yield None, and a caller that got
        the order wrong would silently lose it.
        """
        summary = self._compute_summary()
        items = list(self._held.values())
        self._held.clear()
        return items, summary

    def _compute_summary(self) -> tuple[str, str] | None:
        """One line instead of a burst, once it would be a burst."""
        if len(self._held) < SUMMARY_THRESHOLD:
            return None
        return (
            "BaluHost",
            f"{len(self._held)} neue kritische Meldungen",
        )
