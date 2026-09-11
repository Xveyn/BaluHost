"""Koppel-Sitzung: Sperre, Uebergabe per SHM, Ablauf — ohne D-Bus."""
import asyncio
import os
import time

import pytest

from app.plugins.installed.bluetooth import pairing
from app.plugins.installed.bluetooth.bluez import BlueZError, DeviceInfo
from app.services.monitoring import shm

DEVICE = DeviceInfo(
    path="/org/bluez/hci0/dev_AA_AA_AA_AA_AA_04", adapter_path="/org/bluez/hci0",
    address="AA:AA:AA:AA:AA:04", name="Dev-Tastatur", icon="input-keyboard",
    paired=False, trusted=False, connected=False, battery_percent=None, rssi=None,
)


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(shm, "SHM_DIR", tmp_path / "shm")
    monkeypatch.setattr(pairing, "LOCK_PATH", tmp_path / "pairing.lock")
    monkeypatch.setattr(pairing, "ANSWER_POLL_SECONDS", 0.01)
    monkeypatch.setattr(pairing, "HEARTBEAT_SECONDS", 0.05)
    monkeypatch.setattr(pairing, "RESULT_DISPLAY_SECONDS", 60.0)


@pytest.fixture
async def coord():
    coordinator = pairing.PairingCoordinator()
    yield coordinator
    await coordinator.aclose()


class _FakeBackend:
    def __init__(self, script):
        self.script = script
        self.trusted = []
        self.connected = []
        self.cancelled = []
        self.cancel_event = asyncio.Event()

    async def pair(self, device_path, prompter):
        await self.script(prompter, self)

    async def set_trusted(self, device_path, trusted):
        self.trusted.append((device_path, trusted))

    async def connect(self, device_path):
        self.connected.append(device_path)

    async def cancel_pairing(self, device_path):
        self.cancelled.append(device_path)
        self.cancel_event.set()


class _Finished:
    def __init__(self):
        self.calls = []

    def __call__(self, stage, error):
        self.calls.append((stage, error))


async def _succeed(prompter, backend):
    return None


async def _until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Bedingung nicht erreicht")


def _stage(user_id=1):
    session = pairing.read_session_for(user_id)
    return session.stage if session else None


def test_the_lock_is_exclusive_and_released():
    first, second = pairing.PairingLock(), pairing.PairingLock()
    assert first.acquire() is True
    assert second.acquire() is False
    first.release()
    assert second.acquire() is True
    second.release()


async def test_start_publishes_connecting_for_the_initiator_only(coord):
    release = asyncio.Event()

    async def hold(prompter, backend):
        await release.wait()

    session_id = coord.start(_FakeBackend(hold), DEVICE, 1, _Finished())
    session = pairing.read_session_for(1)
    assert session.session_id == session_id
    assert session.stage == "connecting"
    assert session.address == "AA:AA:AA:AA:AA:04"
    assert pairing.read_session_for(2) is None
    assert pairing.pairing_active() is True
    release.set()
    await coord.wait_idle()


async def test_a_passkey_is_shown_with_progress(coord):
    release = asyncio.Event()

    async def script(prompter, backend):
        prompter.show_passkey(4821, 2)
        await release.wait()

    coord.start(_FakeBackend(script), DEVICE, 1, _Finished())
    await _until(lambda: _stage() == "display_passkey")
    session = pairing.read_session_for(1)
    assert session.code == "004821"
    assert session.entered == 2
    release.set()
    await coord.wait_idle()


async def test_success_trusts_and_connects_and_clears_the_code(coord):
    async def script(prompter, backend):
        prompter.show_passkey(123456, 6)

    backend = _FakeBackend(script)
    finished = _Finished()
    coord.start(backend, DEVICE, 1, finished)
    await coord.wait_idle()
    assert finished.calls == [("succeeded", None)]
    assert backend.trusted == [(DEVICE.path, True)]
    assert backend.connected == [DEVICE.path]
    session = pairing.read_session_for(1)
    assert session.stage == "succeeded"
    assert session.code is None and session.entered is None
    assert pairing.pairing_active() is False


async def test_confirmation_accept_succeeds(coord):
    async def script(prompter, backend):
        if not await prompter.ask_confirmation(654321):
            raise BlueZError("org.bluez.Error.AuthenticationRejected")

    finished = _Finished()
    session_id = coord.start(_FakeBackend(script), DEVICE, 1, finished)
    await _until(lambda: _stage() == "confirm")
    assert pairing.read_session_for(1).code == "654321"
    assert pairing.write_answer(session_id, 1, "accept") is True
    await coord.wait_idle()
    assert finished.calls == [("succeeded", None)]


async def test_confirmation_reject_ends_cancelled(coord):
    async def script(prompter, backend):
        if not await prompter.ask_confirmation(654321):
            raise BlueZError("org.bluez.Error.AuthenticationRejected")

    finished = _Finished()
    session_id = coord.start(_FakeBackend(script), DEVICE, 1, finished)
    await _until(lambda: _stage() == "confirm")
    pairing.write_answer(session_id, 1, "reject")
    await coord.wait_idle()
    assert finished.calls == [("cancelled", None)]


async def test_an_answer_from_another_user_is_refused(coord):
    release = asyncio.Event()

    async def hold(prompter, backend):
        await release.wait()

    session_id = coord.start(_FakeBackend(hold), DEVICE, 1, _Finished())
    assert pairing.write_answer(session_id, 2, "accept") is False
    assert pairing.write_answer("fremde-id", 1, "accept") is False
    release.set()
    await coord.wait_idle()


async def test_cancel_calls_cancel_pairing_and_ends_cancelled(coord):
    async def script(prompter, backend):
        await backend.cancel_event.wait()
        raise BlueZError("org.bluez.Error.AuthenticationCanceled")

    backend = _FakeBackend(script)
    finished = _Finished()
    session_id = coord.start(backend, DEVICE, 1, finished)
    assert pairing.write_answer(session_id, 1, "cancel") is True
    await coord.wait_idle()
    assert backend.cancelled == [DEVICE.path]
    assert finished.calls == [("cancelled", None)]


async def test_a_timeout_cancels_and_fails(coord, monkeypatch):
    monkeypatch.setattr(pairing, "PAIR_TIMEOUT_SECONDS", 0.05)

    async def forever(prompter, backend):
        await asyncio.sleep(10)

    backend = _FakeBackend(forever)
    finished = _Finished()
    coord.start(backend, DEVICE, 1, finished)
    await coord.wait_idle()
    assert finished.calls == [("failed", "timeout")]
    assert backend.cancelled == [DEVICE.path]


async def test_a_second_pairing_is_busy_until_the_first_ends(coord):
    release = asyncio.Event()

    async def hold(prompter, backend):
        await release.wait()

    coord.start(_FakeBackend(hold), DEVICE, 1, _Finished())
    with pytest.raises(pairing.PairingBusy):
        coord.start(_FakeBackend(_succeed), DEVICE, 1, _Finished())
    release.set()
    await coord.wait_idle()
    coord.start(_FakeBackend(_succeed), DEVICE, 1, _Finished())
    await coord.wait_idle()


async def test_a_stale_status_reads_as_nothing(coord, monkeypatch):
    monkeypatch.setattr(pairing, "HEARTBEAT_SECONDS", 60.0)
    release = asyncio.Event()

    async def hold(prompter, backend):
        await release.wait()

    coord.start(_FakeBackend(hold), DEVICE, 1, _Finished())
    old = time.time() - 60
    os.utime(shm.SHM_DIR / pairing.STATUS_FILE, (old, old))
    assert pairing.read_session_for(1) is None
    assert pairing.pairing_active() is False
    release.set()
    await coord.wait_idle()


async def test_already_exists_counts_as_success(coord):
    async def script(prompter, backend):
        raise BlueZError("org.bluez.Error.AlreadyExists")

    finished = _Finished()
    coord.start(_FakeBackend(script), DEVICE, 1, finished)
    await coord.wait_idle()
    assert finished.calls == [("succeeded", None)]


@pytest.mark.parametrize("name,text,expected", [
    ("org.bluez.Error.AuthenticationFailed", "", ("failed", "auth_failed")),
    ("org.bluez.Error.AuthenticationCanceled", "", ("cancelled", None)),
    ("org.bluez.Error.AuthenticationRejected", "", ("cancelled", None)),
    ("org.bluez.Error.AuthenticationTimeout", "", ("failed", "unreachable")),
    ("org.bluez.Error.ConnectionAttemptFailed", "", ("failed", "unreachable")),
    ("org.bluez.Error.Failed", "br-connection-page-timeout", ("failed", "unreachable")),
    ("org.bluez.Error.AlreadyExists", "", ("succeeded", None)),
    ("org.bluez.Error.Failed", "irgendwas", ("failed", "unknown")),
])
def test_outcome_for_error(name, text, expected):
    assert pairing.outcome_for_error(BlueZError(name, text)) == expected
