"""Device code pairing, reusing the flow BaluDesk uses.

Nothing to type in: the tray shows a six digit code, the user approves it in
the web UI, and the pairing can be revoked per device there (which only works
because Task 2 stores the refresh token's jti).
"""

from __future__ import annotations

import socket
import uuid
from dataclasses import dataclass
from pathlib import Path

from baluhost_tray.config import Tokens

# The router carries prefix="/desktop-pairing"; "/api/desktop/..." is not bound.
DEVICE_CODE_PATH = "/api/desktop-pairing/device-code"
POLL_PATH = "/api/desktop-pairing/poll"

_MACHINE_ID_PATHS = (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id"))


class PairingDenied(Exception):
    """The user rejected this device in the web UI."""


class PairingExpired(Exception):
    """The code timed out, or the backend no longer knows it."""


@dataclass(frozen=True)
class PendingPairing:
    device_code: str
    user_code: str
    verification_url: str
    interval: int
    expires_in: int


def device_identity() -> tuple[str, str]:
    """A stable id for this machine plus a human readable name.

    Falls back to a random uuid only if no machine-id is readable; pairing
    still works, the device just shows up as a new one after a reinstall.
    """
    device_id = ""
    for path in _MACHINE_ID_PATHS:
        try:
            device_id = path.read_text().strip()
        except OSError:
            continue
        if device_id:
            break
    if not device_id:
        device_id = str(uuid.uuid4())
    return device_id, f"BaluHost Tray auf {socket.gethostname()}"


def start_pairing(client) -> PendingPairing:
    """Ask the backend for a device code."""
    device_id, device_name = device_identity()
    response = client.post(
        DEVICE_CODE_PATH,
        json={
            "device_id": device_id,
            "device_name": device_name,
            "platform": "linux",
        },
    )
    data = response.json()
    return PendingPairing(
        device_code=data["device_code"],
        user_code=data["user_code"],
        verification_url=data["verification_url"],
        interval=int(data.get("interval", 5)),
        expires_in=int(data.get("expires_in", 600)),
    )


def poll_once(client, device_code: str) -> Tokens | None:
    """One poll. None means keep waiting.

    The status code is read before the body: the route answers 404 for an
    unknown device_code and 429 when the 12/minute limit bites, and neither
    carries a "status" field. Reading the body first turned both into an
    unexplained crash.
    """
    response = client.post(POLL_PATH, json={"device_code": device_code})

    if response.status_code == 429:
        return None            # Limit erreicht — der naechste Versuch kommt eh
    if response.status_code == 404:
        raise PairingExpired("backend does not know this device code")
    if response.status_code >= 500:
        return None            # Serverseitig, voruebergehend
    if response.status_code >= 400:
        raise PairingExpired(f"pairing refused: {response.status_code}")

    data = response.json()
    status = data.get("status")

    if status == "authorization_pending":
        return None
    if status == "denied":
        raise PairingDenied("device was denied in the web UI")
    if status == "expired":
        raise PairingExpired("device code expired before approval")
    if status == "approved":
        return Tokens(access=data["access_token"], refresh=data["refresh_token"])
    raise PairingExpired(f"unexpected pairing status: {status!r}")
