"""BaluHost oeffnen mit Auto-Login: Einmal-Code statt Passwort (#847).

Alles Entscheidbare liegt hier, ohne Qt. Das Tray tauscht seinen Refresh-Token
gegen einen kurzlebigen Code, der Browser bekommt ihn im URL-Fragment
(`#handoff=`), das nie an einen Server geschickt wird. Der Code wird nie
geloggt. Jeder Fehler endet in der Klartext-URL: Oeffnen darf nie scheitern.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Callable

HANDOFF_PATH = "/api/auth/handoff"
HANDOFF_TIMEOUT = 5.0

NOTICE_PIN_INVALID = "PIN stimmt nicht — bitte normal anmelden."
NOTICE_PIN_LOCKED = "PIN gesperrt — bitte mit Passwort anmelden."

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HandoffResult:
    url: str
    notice: str | None = None


def _error(response) -> str | None:
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        return None
    return detail.get("error") if isinstance(detail, dict) else None


def open_url_for(
    session,
    web_url: str,
    pin_enabled: bool,
    ask_pin: Callable[[bool], str | None],
) -> HandoffResult:
    """URL, die der Browser oeffnen soll. Wirft nie."""
    plain = HandoffResult(url=web_url)
    try:
        token = session.current_refresh_token()
        if not token:
            return plain

        pin: str | None = None
        asked = False
        if pin_enabled:
            pin = ask_pin(False)
            if pin is None:
                return plain
            asked = True

        retried = False
        while True:
            response = session.client().post(
                HANDOFF_PATH,
                json={"refresh_token": token, "pin": pin},
                timeout=HANDOFF_TIMEOUT,
            )
            if response.status_code == 200:
                code = response.json()["code"]
                return HandoffResult(url=f"{web_url.rstrip('/')}/login#handoff={code}")

            error = _error(response) if response.status_code == 401 else None
            if error == "pin_required" and not asked:
                pin = ask_pin(False)
                if pin is None:
                    return plain
                asked = True
                continue
            if error == "pin_invalid":
                if retried:
                    return HandoffResult(url=web_url, notice=NOTICE_PIN_INVALID)
                pin = ask_pin(True)
                if pin is None:
                    return plain
                retried = True
                continue
            if error == "pin_locked":
                return HandoffResult(url=web_url, notice=NOTICE_PIN_LOCKED)
            return plain
    except Exception:                       # noqa: BLE001 — Netzwerk, JSON, Dialog
        logger.warning("handoff failed, opening plain URL", exc_info=False)
        return plain


class SingleFlight:
    """Hoechstens ein Ablauf zugleich; weitere Starts werden ignoriert."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running = False

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    def start(self, fn: Callable[[], None]) -> bool:
        with self._lock:
            if self._running:
                return False
            self._running = True

        def _run() -> None:
            try:
                fn()
            finally:
                with self._lock:
                    self._running = False

        try:
            threading.Thread(target=_run, daemon=True).start()
        except Exception:                   # noqa: BLE001
            with self._lock:
                self._running = False
            logger.exception("could not start the handoff thread")
            return False
        return True
