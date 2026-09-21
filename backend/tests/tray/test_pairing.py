"""Tests for the tray's device code pairing."""

from unittest.mock import MagicMock

import pytest

from baluhost_tray import pairing
from baluhost_tray.config import Tokens


def _client(payload: dict, status_code: int = 200) -> MagicMock:
    client = MagicMock()
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    client.post.return_value = response
    return client


def test_start_pairing_uses_the_real_path():
    client = _client({
        "device_code": "dc",
        "user_code": "123456",
        "verification_url": "https://baluhost.local/devices?pair=1",
        "expires_in": 600,
        "interval": 5,
    })

    pending = pairing.start_pairing(client)

    assert pending.user_code == "123456"
    assert pending.interval == 5
    path = client.post.call_args[0][0]
    assert path == "/api/desktop-pairing/device-code"
    body = client.post.call_args[1]["json"]
    assert body["platform"] == "linux"
    assert body["device_id"] and body["device_name"]


def test_poll_uses_the_real_path():
    client = _client({"status": "authorization_pending"})
    pairing.poll_once(client, "dc")
    assert client.post.call_args[0][0] == "/api/desktop-pairing/poll"


def test_poll_pending_returns_none():
    assert pairing.poll_once(_client({"status": "authorization_pending"}), "dc") is None


def test_poll_approved_returns_tokens():
    client = _client({
        "status": "approved",
        "access_token": "at",
        "refresh_token": "rt",
        "token_type": "bearer",
    })
    assert pairing.poll_once(client, "dc") == Tokens(access="at", refresh="rt")


def test_poll_denied_raises():
    with pytest.raises(pairing.PairingDenied):
        pairing.poll_once(_client({"status": "denied"}), "dc")


def test_poll_expired_raises():
    with pytest.raises(pairing.PairingExpired):
        pairing.poll_once(_client({"status": "expired"}), "dc")


def test_rate_limited_means_keep_waiting():
    """429 ist kein Abbruch — die Poll-Route erlaubt nur 12/Minute."""
    assert pairing.poll_once(_client({}, status_code=429), "dc") is None


def test_unknown_device_code_raises_expired_not_typeerror():
    """404 ohne Body darf keinen 'unexpected status: None'-Absturz geben."""
    with pytest.raises(pairing.PairingExpired):
        pairing.poll_once(_client({}, status_code=404), "dc")


def test_server_error_keeps_waiting():
    assert pairing.poll_once(_client({}, status_code=503), "dc") is None


def test_device_identity_is_stable_when_machine_id_is_readable():
    """Runs against the real filesystem: on this host /etc/machine-id is
    readable, so this only exercises that path, never the fallback below."""
    first = pairing.device_identity()
    second = pairing.device_identity()
    assert first == second
    assert first[0] and first[1]


def test_device_identity_fallback_is_persisted_across_restarts(monkeypatch, tmp_path):
    """When neither machine-id file is readable, the generated id must
    survive a tray restart instead of being re-rolled on every call --
    otherwise every restart looks like a new device, the device list fills
    with dead entries, and per-device revocation becomes meaningless.
    """
    missing_path = tmp_path / "no-such-machine-id"
    monkeypatch.setattr(pairing, "_MACHINE_ID_PATHS", (missing_path, missing_path))
    fallback_dir = tmp_path / "baluhost"
    monkeypatch.setattr(pairing, "TOKEN_DIR", fallback_dir)

    first_id, _ = pairing.device_identity()
    second_id, _ = pairing.device_identity()
    assert first_id == second_id

    # device_identity() keeps no in-memory cache, so calling it again is
    # equivalent to a fresh process reading the persisted file from disk.
    third_id, _ = pairing.device_identity()
    assert third_id == first_id

    device_id_file = fallback_dir / "device-id"
    assert device_id_file.read_text().strip() == first_id
    assert (device_id_file.stat().st_mode & 0o777) == 0o600
