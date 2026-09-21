"""Websocket watcher: keeps TrayState in step with the backend.

Ordering matters more than anything else here, but it is established by the
caller: run_cycle opens the socket before loading the snapshot, so the
websockets library holds incoming frames until they are read. The other way
round a snapshot would undo a "read" the socket already reported, and the
icon would jump back to red.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field

from baluhost_tray.state import PendingPopup, TrayState

logger = logging.getLogger(__name__)

POPUP_TYPES = frozenset({"critical"})
COLOURING_TYPES = frozenset({"critical", "warning"})
BULK_ACTIONS = frozenset({"read_all", "dismissed_all", "deleted_all"})
SNAPSHOT_PATH = "/api/notifications"
SNAPSHOT_PAGE_SIZE = 100


def backoff_delays(attempts: int, base: float = 1.0, cap: float = 60.0) -> list[float]:
    """Exponential backoff with jitter, capped.

    The jitter is not decoration: without it every client that dropped when
    the backend restarted comes back at the same instant.
    """
    return [
        round(min(cap, base * (2 ** attempt)) * random.uniform(0.5, 1.0), 3)
        for attempt in range(attempts)
    ]


@dataclass
class FrameOutcome:
    popups: list[PendingPopup] = field(default_factory=list)
    reload_needed: bool = False


class Watcher:
    def __init__(self, session, state: TrayState) -> None:
        self._session = session
        self._state = state

    def load_snapshot(self) -> bool:
        """Replace state from REST. Returns False if the snapshot failed.

        unread_only matters: without it the route returns everything newest
        first, capped at 100 rows, and an older unread notification would
        fall off the page — green icon, unread server.
        """
        try:
            response = self._session.client().get(
                SNAPSHOT_PATH,
                params={"unread_only": True, "page_size": SNAPSHOT_PAGE_SIZE},
            )
        except Exception as exc:
            logger.warning("snapshot request failed: %s", exc)
            return False

        if response.status_code != 200:
            # Never treat this as success: the loop would go on to claim
            # "connected" while showing stale state.
            logger.warning("snapshot refused: %s", response.status_code)
            return False

        body = response.json()
        items = [
            (int(raw["id"]), str(raw.get("notification_type", "")))
            for raw in body.get("notifications", [])
            if not raw.get("is_read")
        ]
        self._state.apply_snapshot(items)

        reported = body.get("unread_count")
        if isinstance(reported, int) and reported != len(items):
            # More unread than one page holds, or a filter surprise. The
            # count is the server's own answer, so trust it over our page.
            logger.info(
                "snapshot page holds %d of %d unread notifications",
                len(items), reported,
            )
        return True

    def handle_frame(self, frame: dict) -> FrameOutcome:
        """Apply one frame."""
        kind = frame.get("type")
        payload = frame.get("payload") or {}

        if kind == "notification":
            ntype = str(payload.get("notification_type", ""))
            nid = int(payload.get("id", 0))
            if ntype in COLOURING_TYPES:
                self._state.add(nid, ntype)
            if ntype in POPUP_TYPES:
                return FrameOutcome(popups=[PendingPopup(
                    notification_id=nid,
                    title=str(payload.get("title", "BaluHost")),
                    message=str(payload.get("message", "")),
                )])
            return FrameOutcome()

        if kind == "notification_state":
            action = payload.get("action")
            if action in BULK_ACTIONS:
                # The bulk actions carry no ids because mark_all_as_read may
                # have been scoped to a category. Clearing would be a guess.
                return FrameOutcome(reload_needed=True)
            self._state.remove([int(i) for i in payload.get("ids", [])])
            return FrameOutcome()

        return FrameOutcome()
