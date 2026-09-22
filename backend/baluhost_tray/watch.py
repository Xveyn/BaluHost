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
from collections import OrderedDict
from dataclasses import dataclass, field

from baluhost_tray.session import AuthExpired
from baluhost_tray.state import PendingPopup, TrayState

logger = logging.getLogger(__name__)

POPUP_TYPES = frozenset({"critical"})
COLOURING_TYPES = frozenset({"critical", "warning"})
BULK_ACTIONS = frozenset({"read_all", "dismissed_all", "deleted_all"})
SNAPSHOT_PATH = "/api/notifications"
SNAPSHOT_PAGE_SIZE = 100
# Wie viele Meldungs-Ids sich das Tray merkt. Ein Tray laeuft wochenlang; ohne
# Deckel waechst die Menge mit jeder Meldung mit. Eine Snapshot-Seite fasst 100
# Zeilen, das hier ist also Platz fuer mehrere Seiten plus laufende Frames.
SEEN_IDS_LIMIT = 512


def backoff_delays(attempts: int, base: float = 1.0, cap: float = 60.0) -> list[float]:
    """Exponential backoff with jitter, capped.

    The jitter is not decoration: without it every client that dropped when
    the backend restarted comes back at the same instant.
    """
    return [
        round(min(cap, base * (2 ** attempt)) * random.uniform(0.5, 1.0), 3)
        for attempt in range(attempts)
    ]


def _as_int(value) -> int | None:
    """int() that reports failure instead of raising.

    Ids arrive as whatever the server put on the wire; a string of digits is
    fine, "abc" or None is not, and neither is worth a reconnect.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass
class FrameOutcome:
    popups: list[PendingPopup] = field(default_factory=list)
    reload_needed: bool = False


@dataclass
class SnapshotOutcome:
    """Wie FrameOutcome, nur fuer den Neuabgleich.

    `ok` traegt weiter genau die Bedeutung des frueheren `-> bool`: False
    bricht den Zyklus ab, statt "verbunden" zu behaupten. `popups` kommt dazu,
    weil der Neuabgleich seit #685 auch Meldungen nachreicht, deren Frame das
    Tray nie erreicht hat. Beides zusammen in einem Rueckgabewert, damit keine
    Aufrufstelle die Popups stillschweigend fallen lassen kann.
    """

    ok: bool = False
    popups: list[PendingPopup] = field(default_factory=list)


class SeenIds:
    """Beschraenktes Gedaechtnis: welche Meldungen das Tray schon kannte.

    Eine echte Menge, keine Hochwassermarke. Nur die hoechste gesehene Id zu
    merken waere O(1) und von selbst beschraenkt — und ginge am Fehlerbild
    vorbei: das Tray haengt an einem Worker, der die kritischen
    Hardware-Meldungen nicht sendet, andere Meldungen aber schon. Kommt Meldung
    100 per Frame an, waehrend die kritische 99 verpasst wurde, gaelte 99 unter
    einer Marke fuer immer als gesehen.

    Verdraengt wird das aelteste Auftauchen, nicht der aelteste Eintrag: was in
    jedem Neuabgleich wieder mitkommt — also alles dauerhaft Ungelesene —,
    rutscht dabei nach vorn und faellt nicht heraus.

    Laeuft die Menge trotzdem ueber, kann eine sehr alte ungelesene kritische
    Meldung einmal erneut poppen. Das ist die bewusst gewaehlte Richtung:
    lieber ein Popup zu viel als ein verschluckter Alarm.
    """

    def __init__(self, limit: int = SEEN_IDS_LIMIT) -> None:
        self._limit = limit
        self._ids: OrderedDict[int, None] = OrderedDict()

    def __contains__(self, notification_id: int) -> bool:
        return notification_id in self._ids

    def __len__(self) -> int:
        return len(self._ids)

    def add(self, notification_id: int) -> None:
        if notification_id in self._ids:
            self._ids.move_to_end(notification_id)
            return
        self._ids[notification_id] = None
        while len(self._ids) > self._limit:
            self._ids.popitem(last=False)


class Watcher:
    def __init__(self, session, state: TrayState) -> None:
        self._session = session
        self._state = state
        # Gehoert hierher und nicht in TrayState: apply_snapshot() ersetzt den
        # Zustand bei jedem Abgleich, und mit ihm wuerde das Gedaechtnis
        # zuruecksetzen, das genau *ueber* Abgleiche hinweg halten muss. Der
        # Watcher lebt so lange wie der Prozess, auch ueber Reconnects hinweg:
        # run_loop behaelt denselben LoopContext.
        self._seen = SeenIds()
        self._primed = False

    def load_snapshot(self) -> SnapshotOutcome:
        """Replace state from REST, and catch up popups that never arrived.

        unread_only matters: without it the route returns everything newest
        first, capped at 100 rows, and an older unread notification would
        fall off the page — green icon, unread server.

        Das Nachreichen ist eine Milderung, keine Loesung: in Produktion laufen
        vier Uvicorn-Worker gegen einen prozesslokalen WebSocketManager, und ein
        Broadcast erreicht nur die Verbindungen seines eigenen Prozesses
        (Issue #685). Ein verpasster Frame war damit nicht verspaetet, sondern
        endgueltig weg. Aus "nie" wird hier "spaetestens beim naechsten
        Abgleich".
        """
        try:
            response = self._session.client().get(
                SNAPSHOT_PATH,
                params={"unread_only": True, "page_size": SNAPSHOT_PAGE_SIZE},
            )
        except Exception as exc:
            logger.warning("snapshot request failed: %s", exc)
            return SnapshotOutcome()

        if response.status_code == 401:
            # Abgelaufenes Access-Token, und das ist etwas anderes als ein
            # voruebergehender Fehlschlag. `ok=False` laesst run_cycle den
            # Zyklus mit demselben Token wiederholen — der naechste Abgleich
            # bekommt wieder 401, und so weiter.
            #
            # Am 2026-09-22 in Produktion beobachtet: das Tray lief ueber
            # Minuten im Sekundentakt in "snapshot refused: 401", ohne einen
            # einzigen Refresh-Versuch. Bis dahin kannte nur session.ws_token()
            # den 401 als "Token abgelaufen" — und der wird nicht mehr
            # aufgerufen, solange die WebSocket-Verbindung steht, denn die
            # authentifiziert sich nicht neu. Das Tray kam also gar nicht an
            # die Stelle, die das Token erneuert haette, und blieb bis zum
            # naechsten Verbindungsabriss auf einem eingefrorenen Stand
            # stehen — samt ausgefallenem Nachreichen verpasster Popups, das
            # ja genau an diesem Abgleich haengt.
            #
            # AuthExpired ist der Weg nach draussen: run_loop faengt es,
            # erneuert das Token und beginnt einen neuen Zyklus. Nur 401 —
            # ein 429 oder 500 hier zu refreshen wuerde die ws-token-Quote
            # leerlaufen lassen, an der die Kopplung haengt.
            raise AuthExpired("snapshot rejected the access token")

        if response.status_code != 200:
            # Never treat this as success: the loop would go on to claim
            # "connected" while showing stale state.
            logger.warning("snapshot refused: %s", response.status_code)
            return SnapshotOutcome()

        try:
            body = response.json()
            items = [
                (
                    int(raw["id"]),
                    str(raw.get("notification_type", "")),
                    # Titel und Text werden mitgezogen, weil ein nachgereichtes
                    # Popup beides braucht. Fehlen sie, ist das kein
                    # Fehlschlag: der ok-Vertrag deckt Transport, Status,
                    # kaputtes JSON und eine fehlende id ab — nicht einen
                    # fehlenden Titel.
                    str(raw.get("title", "BaluHost")),
                    str(raw.get("message", "")),
                )
                for raw in body.get("notifications", [])
                if not raw.get("is_read")
            ]
            self._state.apply_snapshot([(nid, ntype) for nid, ntype, _t, _m in items])
        except (ValueError, KeyError, TypeError) as exc:
            # A 200 with broken JSON or a row missing "id" is still not a
            # success -- the ok contract covers parsing, not just the
            # transport. Kept as its own except (and its own log line, not
            # the "refused" one above) so the two failure modes stay
            # distinguishable in the log. A bare programming mistake
            # (AttributeError from a typo) is deliberately not caught here
            # and keeps propagating.
            logger.warning("snapshot body unusable: %s", exc)
            return SnapshotOutcome()

        popups = self._catch_up(items)

        reported = body.get("unread_count")
        if isinstance(reported, int) and reported != len(items):
            # More unread than one page holds, or a filter surprise. The
            # count is the server's own answer, so trust it over our page.
            logger.info(
                "snapshot page holds %d of %d unread notifications",
                len(items), reported,
            )
        return SnapshotOutcome(ok=True, popups=popups)

    def _catch_up(self, items: list[tuple[int, str, str, str]]) -> list[PendingPopup]:
        """Popups fuer kritische Meldungen, die das Tray nie zu Gesicht bekam.

        Der erste Abgleich nach Prozessstart erzeugt nichts. Dort ist alles
        Ungelesene per Definition "noch nie gesehen", und jedes
        `systemctl --user restart` begruesste den Nutzer sonst mit einer
        Popup-Lawine fuer den gesamten Bestand. Er merkt sich nur.
        """
        first_run, self._primed = not self._primed, True
        popups: list[PendingPopup] = []
        for nid, ntype, title, message in items:
            known = nid in self._seen
            # Auch Bekanntes geht durch add(): das haelt alles dauerhaft
            # Ungelesene vorn in der Verdraengungsreihenfolge, statt es
            # ausgerechnet dann zu vergessen, wenn es noch offen ist.
            self._seen.add(nid)
            if known or first_run or ntype not in POPUP_TYPES:
                continue
            popups.append(PendingPopup(
                notification_id=nid,
                title=title,
                message=message,
            ))
        return popups

    def handle_frame(self, frame: dict) -> FrameOutcome:
        """Apply one frame.

        An unusable frame is treated like an unknown type: empty outcome, and
        the caller's round carries on. Raising would cost a full reconnect over
        a single broken field — exactly the reaction run_cycle's _parse_frame()
        drops one level up, so raising here would put it back.
        """
        kind = frame.get("type")
        payload = frame.get("payload")
        if not isinstance(payload, dict):
            payload = {}

        if kind == "notification":
            ntype = str(payload.get("notification_type", ""))
            # No default: a missing id is exactly as unusable as a broken one.
            # `payload.get("id", 0)` would quietly apply notification 0 when
            # the field is absent, while "id": null threw the frame away.
            nid = _as_int(payload.get("id"))
            if nid is None:
                logger.warning("notification frame without a usable id, ignored")
                return FrameOutcome()
            # Live gesehen ist gesehen: der naechste Neuabgleich darf diese
            # Meldung nicht ein zweites Mal als "nie gesehen" nachreichen. Nur
            # merken, nicht filtern — ein Frame loest sein Popup weiterhin
            # unbesehen aus, denn ein Popup zu viel ist besser als ein
            # verschluckter Alarm.
            self._seen.add(nid)
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
            raw_ids = payload.get("ids", [])
            if not isinstance(raw_ids, (list, tuple)):
                logger.warning("state frame with unusable ids, ignored")
                return FrameOutcome()
            ids = [nid for nid in (_as_int(i) for i in raw_ids) if nid is not None]
            if len(ids) != len(raw_ids):
                # Apply what is usable rather than dropping the whole frame:
                # the ids we understood are still true.
                logger.warning(
                    "state frame carried %d unusable id(s), applying the rest",
                    len(raw_ids) - len(ids),
                )
            self._state.remove(ids)
            return FrameOutcome()

        return FrameOutcome()
