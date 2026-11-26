"""Always Awake direkt im Tray-Menue (#847).

Alles Entscheidbare liegt hier, ohne Qt. Die Rechte entscheidet das Backend
(`/api/system/sleep/config` ist Admin-only); das Tray blendet das Untermenue nur aus,
wenn der Nutzer kein Admin ist. Der angezeigte Stand kommt immer aus der
Antwort des Backends — es darf die Frist kuerzen (Kernzeitfenster).

Gelesen wird der Sleep-*Status*, nicht die Konfiguration: nur er sagt, ob gerade
ein Kernzeitfenster laeuft. Eine Frist, die keinem Menueeintrag entspricht (in
der Web-UI frei gewaehlt), zeigt das Tray als eigenen, nicht anklickbaren
Eintrag an — setzen kann man so eine Frist nur in der Web-UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable

import httpx

# Der Sleep-Router haengt unter prefix="/system/sleep"; "/api/sleep/..." ist nicht gebunden.
SLEEP_CONFIG_PATH = "/api/system/sleep/config"
# Lesen ueber den Status: er traegt Always Awake *und* das laufende Kernzeitfenster.
SLEEP_STATUS_PATH = "/api/system/sleep/status"
REQUEST_TIMEOUT = 5.0


class AwakeChoice(Enum):
    OFF = "off"
    HOUR = "hour"
    EIGHT_HOURS = "eight_hours"
    PERMANENT = "permanent"


@dataclass(frozen=True)
class AwakeState:
    enabled: bool
    until: datetime | None
    # Laufendes Kernzeitfenster: das System bleibt dann ohnehin wach.
    core_active: bool = False
    core_label: str | None = None
    core_until: datetime | None = None


class AwakeError(Exception):
    """Abruf oder Setzen ist gescheitert (Text ist nicht fuer Nutzer gedacht)."""


def payload_for(choice: AwakeChoice, now_utc: datetime) -> dict:
    if choice is AwakeChoice.OFF:
        return {"always_awake_enabled": False, "always_awake_until": None}
    if choice is AwakeChoice.PERMANENT:
        return {"always_awake_enabled": True, "always_awake_until": None}
    hours = 1 if choice is AwakeChoice.HOUR else 8
    return {
        "always_awake_enabled": True,
        "always_awake_until": (now_utc + timedelta(hours=hours)).isoformat(),
    }


def _parse_time(raw: object) -> datetime | None:
    if not raw:
        return None
    # Python < 3.11 kennt "Z" in fromisoformat nicht. Ein Zeitpunkt ohne Zone
    # (Kernzeitfenster rechnet das Backend in Ortszeit) bleibt naiv;
    # `astimezone()` liest ihn dann als Ortszeit — genau das ist er.
    return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))


def parse_state(data: dict) -> AwakeState:
    """Antwort von `/api/system/sleep/status` lesen."""
    try:
        awake = data.get("always_awake") or {}
        core = data.get("core_uptime") or {}
        core_active = bool(core.get("active"))
        label = core.get("current_window_label") if core_active else None
        return AwakeState(
            enabled=bool(awake.get("enabled")),
            until=_parse_time(awake.get("until")),
            core_active=core_active,
            core_label=str(label) if label else None,
            core_until=_parse_time(core.get("current_window_ends_at")) if core_active else None,
        )
    except (ValueError, AttributeError, TypeError) as exc:
        raise AwakeError(f"unlesbare Antwort: {exc}") from exc


def checked_choice(state: AwakeState) -> AwakeChoice | None:
    """Welcher waehlbare Eintrag den Haken traegt; `None` = befristet.

    Eine Frist entspricht nie genau "1 Stunde" oder "8 Stunden" — die zaehlen
    ab dem Klick. Den Haken traegt dann der Frist-Eintrag (`deadline_text`).
    """
    if not state.enabled:
        return AwakeChoice.OFF
    if state.until is None:
        return AwakeChoice.PERMANENT
    return None


def _clock(moment: datetime, now: datetime) -> str:
    """"14:30" heute, sonst "27.11. 14:30" (Fristen reichen bis 7 Tage)."""
    local = moment.astimezone()
    if local.date() == now.astimezone().date():
        return f"{local:%H:%M}"
    return f"{local:%d.%m. %H:%M}"


def deadline_text(state: AwakeState, now: datetime) -> str | None:
    """Beschriftung des Frist-Eintrags; `None` = keine Frist, Eintrag verbergen."""
    if not state.enabled or state.until is None:
        return None
    return f"Bis {_clock(state.until, now)}"


def core_text(state: AwakeState, now: datetime) -> str | None:
    """Hinweiszeile fuer ein laufendes Kernzeitfenster; `None` = keins aktiv."""
    if not state.core_active:
        return None
    name = f"Kernzeit „{state.core_label}“" if state.core_label else "Kernzeit"
    if state.core_until is None:
        return f"{name} aktiv"
    return f"{name} bis {_clock(state.core_until, now)}"


def submenu_title(state: AwakeState, now: datetime) -> str:
    if state.enabled and state.until is not None:
        return f"Always Awake — bis {_clock(state.until, now)}"
    if state.enabled:
        return "Always Awake"
    if state.core_active:
        # Aus, aber wach durch die Kernzeit: das soll man ohne Aufklappen sehen.
        if state.core_until is not None:
            return f"Always Awake — Kernzeit bis {_clock(state.core_until, now)}"
        return "Always Awake — Kernzeit"
    return "Always Awake"


def _request(send: Callable[[], object], on_auth_expired: Callable[[], None]) -> object:
    """Genau ein Refresh bei 401; alles andere ausser 200 ist ein AwakeError."""
    refreshed = False
    while True:
        try:
            response = send()
        except httpx.HTTPError as exc:
            raise AwakeError(f"Netzwerkfehler: {exc}") from exc
        status = response.status_code
        if status == 401 and not refreshed:
            try:
                on_auth_expired()
            except Exception as exc:        # noqa: BLE001 — PairingLost, Netz, alles
                raise AwakeError(f"Token-Erneuerung fehlgeschlagen: {exc}") from exc
            refreshed = True
            continue
        if status != 200:
            raise AwakeError(f"HTTP {status}")
        return response


def fetch_state(client, on_auth_expired: Callable[[], None]) -> AwakeState:
    response = _request(
        lambda: client.get(SLEEP_STATUS_PATH, timeout=REQUEST_TIMEOUT),
        on_auth_expired,
    )
    try:
        data = response.json()
    except ValueError as exc:
        raise AwakeError(f"keine JSON-Antwort: {exc}") from exc
    if not isinstance(data, dict):
        raise AwakeError("unlesbare Antwort: kein Objekt")
    return parse_state(data)


def apply(
    client,
    choice: AwakeChoice,
    now_utc: datetime,
    on_auth_expired: Callable[[], None],
) -> AwakeState:
    """Setzen, dann den Status neu lesen.

    Die PUT-Antwort ist die Konfiguration und kennt kein Kernzeitfenster;
    ausserdem kuerzt das Backend die Frist womoeglich. Angezeigt wird also,
    was der Status danach sagt, nicht was gewaehlt wurde.
    """
    payload = payload_for(choice, now_utc)
    _request(
        lambda: client.put(SLEEP_CONFIG_PATH, json=payload, timeout=REQUEST_TIMEOUT),
        on_auth_expired,
    )
    return fetch_state(client, on_auth_expired)
