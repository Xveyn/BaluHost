"""Device code pairing, reusing the flow BaluDesk uses.

Nothing to type in: the tray shows a six digit code, the user approves it in
the web UI, and the pairing can be revoked per device there (which only works
because Task 2 stores the refresh token's jti).
"""

from __future__ import annotations

import os
import socket
import uuid
from dataclasses import dataclass
from pathlib import Path

from baluhost_tray.config import TOKEN_DIR, Tokens

# The router carries prefix="/desktop-pairing"; "/api/desktop/..." is not bound.
DEVICE_CODE_PATH = "/api/desktop-pairing/device-code"
POLL_PATH = "/api/desktop-pairing/poll"

_MACHINE_ID_PATHS = (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id"))
_DEVICE_ID_FILENAME = "device-id"


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

    Prefers the system machine-id. Where neither machine-id file is
    readable, a fallback id is generated once and persisted to
    ~/.baluhost/device-id (config.TOKEN_DIR, the same directory the token
    store uses), so a tray restart still presents the same device instead
    of registering as a new one each time -- which would otherwise fill the
    device list with dead entries and make per-device revocation pointless.
    Only if that file can neither be read nor written does this fall back
    further, to a uuid that is volatile for just this one call.
    """
    device_id = _read_machine_id()
    if not device_id:
        device_id = _persistent_fallback_id()
    return device_id, f"BaluHost Tray auf {socket.gethostname()}"


def _read_machine_id() -> str:
    for path in _MACHINE_ID_PATHS:
        try:
            value = path.read_text().strip()
        except OSError:
            continue
        if value:
            return value
    return ""


def _persistent_fallback_id() -> str:
    """Reuse a previously generated id, or generate and persist a new one.

    Mirrors config.save_tokens()'s handling of permissions: directory
    0o700, file 0o600, mode set in the open() call itself so the file is
    never briefly world-readable in between.
    """
    device_id_file = TOKEN_DIR / _DEVICE_ID_FILENAME

    try:
        existing = device_id_file.read_text().strip()
        if existing:
            return existing
    except OSError:
        pass

    new_id = str(uuid.uuid4())
    try:
        TOKEN_DIR.mkdir(parents=True, exist_ok=True)
        os.chmod(TOKEN_DIR, 0o700)
        fd = os.open(device_id_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, new_id.encode("utf-8"))
        finally:
            os.close(fd)
        os.chmod(device_id_file, 0o600)
    except OSError:
        pass  # Persistence failed -- this id is volatile for this call only.

    return new_id


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
