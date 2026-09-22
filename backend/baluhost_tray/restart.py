"""The tray's outgoing path: restarting the BaluHost services.

Everything decidable lives here so it can be tested without Qt, without
systemd and without a running backend. tray.py only shows dialogs.

Two routes, deliberately: while the API answers, the backend restarts its own
units after a BaluHost step-up. When it does not answer, nobody can verify a
BaluHost password any more — then systemd does the work and polkit asks the
question that still has an honest answer.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Sequence

import httpx

HEALTH_PATH = "/api/health"
ME_PATH = "/api/auth/me"
TOTP_STATUS_PATH = "/api/auth/2fa/status"
RESTART_ALL_PATH = "/api/system/restart-all"

# Long enough that a busy backend still counts as alive, short enough that the
# dialog does not feel stuck in the case this feature exists for.
PROBE_TIMEOUT = 2.0
# The API path restarts four units synchronously (20 s each in the worst case)
# before it answers. Below that, a slow restart would look like a dead backend.
API_TIMEOUT = 120.0
LOCAL_TIMEOUT = 120.0

UNITS: tuple[str, ...] = (
    "baluhost-scheduler",
    "baluhost-monitoring",
    "baluhost-webdav",
    "baluhost-backend-local",
    "baluhost-backend",
)


@dataclass(frozen=True)
class RestartOutcome:
    """What happened, and what the dialog should do next."""

    ok: bool
    message: str
    retry_secret: bool = False   # wrong password/code — ask again
    offer_local: bool = False    # API died mid-flight — offer the fallback


@dataclass(frozen=True)
class AccountFacts:
    """``is_admin is None`` means "could not ask", not "not an admin"."""

    is_admin: bool | None
    totp_enabled: bool


_UNKNOWN = AccountFacts(is_admin=None, totp_enabled=False)


def probe_api(client) -> bool:
    """Does the API answer right now?

    Deliberately not derived from the icon colour: that one tracks the
    websocket, and a stale ws-token paints the icon grey while /api/health is
    perfectly fine.
    """
    try:
        return client.get(HEALTH_PATH, timeout=PROBE_TIMEOUT).status_code == 200
    except httpx.HTTPError:
        return False


def fetch_account_facts(
    client,
    on_auth_expired: Callable[[], None] | None = None,
) -> AccountFacts:
    """Role and 2FA state of the paired account. Never raises.

    Refreshes once on a 401: an expired access token is the normal state at
    tray start (#692), and without the retry a 2FA account would be asked three
    times for a password the route does not accept.
    """
    refreshed = False
    while True:
        try:
            response = client.get(ME_PATH, timeout=PROBE_TIMEOUT)
        except httpx.HTTPError:
            return _UNKNOWN

        if response.status_code == 401 and on_auth_expired is not None and not refreshed:
            try:
                on_auth_expired()
            except Exception:       # noqa: BLE001 — PairingLost, TemporaryFailure, network, anything
                return _UNKNOWN
            refreshed = True
            continue

        if response.status_code != 200:
            return _UNKNOWN

        try:
            is_admin = response.json().get("role") == "admin"
        except (ValueError, AttributeError):
            return _UNKNOWN
        break

    totp_enabled = False
    try:
        status_response = client.get(TOTP_STATUS_PATH, timeout=PROBE_TIMEOUT)
        if status_response.status_code == 200:
            totp_enabled = bool(status_response.json().get("enabled"))
    except (httpx.HTTPError, ValueError, AttributeError):
        # A missing 2FA state only mislabels the dialog, and the route's 401
        # carries `totp_required` anyway.
        pass

    return AccountFacts(is_admin=is_admin, totp_enabled=totp_enabled)


def menu_visible(is_admin: bool | None, api_reachable: bool) -> bool:
    """Show the entry for admins — and for anyone when we could not ask.

    The middle case is the point: without it the button would be missing in
    exactly the situation it exists for, where the backend has been dead since
    login and the role was never learned. It weakens nothing, because on that
    route polkit decides, not the visibility of a menu entry.
    """
    if is_admin:
        return True
    if is_admin is None:
        return True
    return not api_reachable
