"""Always Awake direkt im Tray-Menue (#847).

Alles Entscheidbare liegt hier, ohne Qt. Die Rechte entscheidet das Backend
(`/api/sleep/config` ist Admin-only); das Tray blendet das Untermenue nur aus,
wenn der Nutzer kein Admin ist. Der angezeigte Stand kommt immer aus der
Antwort des Backends — es darf die Frist kuerzen (Kernzeitfenster).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable

import httpx

SLEEP_CONFIG_PATH = "/api/sleep/config"
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


def parse_state(data: dict) -> AwakeState:
    try:
        enabled = bool(data.get("always_awake_enabled"))
        raw = data.get("always_awake_until")
        until = None
        if raw:
            # Python < 3.11 kennt "Z" in fromisoformat nicht.
            until = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return AwakeState(enabled=enabled, until=until)
    except (ValueError, AttributeError, TypeError) as exc:
        raise AwakeError(f"unlesbare Antwort: {exc}") from exc


def checked_choice(state: AwakeState) -> AwakeChoice | None:
    """Welcher Eintrag den Haken traegt; `None` = befristet, kein Eintrag passt."""
    if not state.enabled:
        return AwakeChoice.OFF
    if state.until is None:
        return AwakeChoice.PERMANENT
    return None


def submenu_title(state: AwakeState) -> str:
    if state.enabled and state.until is not None:
        return f"Always Awake — bis {state.until.astimezone():%H:%M}"
    return "Always Awake"


def _request(send: Callable[[], object], on_auth_expired: Callable[[], None]) -> AwakeState:
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
        try:
            return parse_state(response.json())
        except ValueError as exc:
            raise AwakeError(f"keine JSON-Antwort: {exc}") from exc


def fetch_state(client, on_auth_expired: Callable[[], None]) -> AwakeState:
    return _request(
        lambda: client.get(SLEEP_CONFIG_PATH, timeout=REQUEST_TIMEOUT),
        on_auth_expired,
    )


def apply(
    client,
    choice: AwakeChoice,
    now_utc: datetime,
    on_auth_expired: Callable[[], None],
) -> AwakeState:
    payload = payload_for(choice, now_utc)
    return _request(
        lambda: client.put(SLEEP_CONFIG_PATH, json=payload, timeout=REQUEST_TIMEOUT),
        on_auth_expired,
    )
