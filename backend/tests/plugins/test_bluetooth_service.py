"""Service: Adapterwahl, LAN-Pruefung, Validierung vor jedem Backend-Aufruf."""
import asyncio

import pytest

from app.core.config import settings
from app.core.exceptions import (
    BadGatewayError,
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)
from app.plugins.installed.bluetooth import pairing
from app.plugins.installed.bluetooth import service as service_module
from app.plugins.installed.bluetooth.backend import DevBluetoothBackend
from app.plugins.installed.bluetooth.bluez import BlueZError
from app.plugins.installed.bluetooth.service import BluetoothService
from app.services.monitoring import shm

LAN = "192.168.1.10"
PUBLIC = "203.0.113.7"
KEYBOARD = "AA:AA:AA:AA:AA:04"


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(shm, "SHM_DIR", tmp_path / "shm")
    monkeypatch.setattr(pairing, "LOCK_PATH", tmp_path / "pairing.lock")
    monkeypatch.setattr(pairing, "ANSWER_POLL_SECONDS", 0.01)
    monkeypatch.setattr(pairing, "RESULT_DISPLAY_SECONDS", 60.0)
    monkeypatch.setattr(service_module, "is_private_or_local_ip", lambda host: host == LAN)
    monkeypatch.setattr(settings, "bluetooth_adapter_address", "")


@pytest.fixture
async def backend():
    return DevBluetoothBackend(step_seconds=0, passkey=482913)


@pytest.fixture
async def svc(backend):
    # Langes Scan-Fenster: ein kurzes wuerde ungekoppelte Funde mitten in einer
    # laufenden Kopplung wieder entfernen. TestScan baut sich ein eigenes.
    service = BluetoothService(backend=backend, scan_seconds=300)
    yield service
    await service.aclose()


def _spy_pair(backend):
    calls = []
    original = backend.pair

    async def spy(path, prompter):
        calls.append(path)
        await original(path, prompter)

    backend.pair = spy
    return calls


class TestState:
    async def test_it_lists_the_paired_devices_with_their_kinds(self, svc):
        state = await svc.get_state(LAN)
        assert state.available is True
        assert state.adapter.address == "AA:AA:AA:AA:AA:01"
        kinds = {d.name: d.kind for d in state.devices}
        assert kinds == {"Xbox Wireless Controller": "controller", "JBL TUNE510BT": "audio"}

    async def test_can_pair_here_follows_the_client_ip(self, svc):
        assert (await svc.get_state(LAN)).can_pair_here is True
        assert (await svc.get_state(PUBLIC)).can_pair_here is False
        assert (await svc.get_state(None)).can_pair_here is False

    async def test_a_missing_configured_adapter_is_unavailable_not_a_fallback(self, svc, monkeypatch):
        monkeypatch.setattr(settings, "bluetooth_adapter_address", "AA:AA:AA:AA:AA:09")
        state = await svc.get_state(LAN)
        assert state.available is False
        assert "AA:AA:AA:AA:AA:09" in state.detail
        assert state.devices == []

    async def test_a_dead_bluez_reads_as_unavailable(self, backend, svc):
        async def broken():
            raise BlueZError("org.baluhost.Error.BusUnavailable", "EOFError")
        backend.snapshot = broken
        state = await svc.get_state(LAN)
        assert state.available is False
        assert state.detail


class TestPairingGate:
    async def test_pairing_from_outside_the_lan_is_forbidden_before_any_backend_call(self, backend, svc):
        await svc.start_scan()
        calls = _spy_pair(backend)
        with pytest.raises(ForbiddenError):
            await svc.start_pairing(KEYBOARD, 1, PUBLIC, lambda *a: None)
        assert calls == []

    async def test_a_malformed_address_is_400(self, svc):
        with pytest.raises(BadRequestError):
            await svc.start_pairing("/org/bluez/hci0", 1, LAN, lambda *a: None)

    async def test_an_unknown_address_is_404_without_a_backend_call(self, backend, svc):
        calls = _spy_pair(backend)
        with pytest.raises(NotFoundError):
            await svc.start_pairing("AA:AA:AA:AA:AA:77", 1, LAN, lambda *a: None)
        assert calls == []

    async def test_an_already_paired_device_is_409(self, svc):
        with pytest.raises(ConflictError):
            await svc.start_pairing("AA:AA:AA:AA:AA:02", 1, LAN, lambda *a: None)

    async def test_a_second_pairing_is_409(self, backend, svc):
        await svc.start_scan()
        release = asyncio.Event()

        async def hold(path, prompter):
            await release.wait()

        backend.pair = hold
        await svc.start_pairing(KEYBOARD, 1, LAN, lambda *a: None)
        with pytest.raises(ConflictError):
            await svc.start_pairing("AA:AA:AA:AA:AA:05", 1, LAN, lambda *a: None)
        release.set()
        await svc.wait_pairings()


class TestPairingFlow:
    async def test_a_keyboard_pairs_trusts_and_connects(self, svc):
        await svc.start_scan()
        finished = []
        session_id = await svc.start_pairing(
            KEYBOARD.lower(), 1, LAN, lambda device, stage, error: finished.append((device.address, stage, error)),
        )
        await svc.wait_pairings()
        assert finished == [(KEYBOARD, "succeeded", None)]
        status = svc.pairing_status(1)
        assert status.session_id == session_id and status.stage == "succeeded"
        keyboard = next(d for d in (await svc.get_state(LAN)).devices if d.address == KEYBOARD)
        assert keyboard.paired and keyboard.trusted and keyboard.connected

    async def test_the_status_is_invisible_to_other_users(self, svc):
        await svc.start_scan()
        await svc.start_pairing(KEYBOARD, 1, LAN, lambda *a: None)
        assert svc.pairing_status(2) is None
        await svc.wait_pairings()

    async def test_confirming_from_outside_the_lan_is_forbidden_but_cancelling_is_not(self, backend, svc):
        await svc.start_scan()
        release = asyncio.Event()

        async def hold(path, prompter):
            await release.wait()

        backend.pair = hold
        session_id = await svc.start_pairing(KEYBOARD, 1, LAN, lambda *a: None)
        with pytest.raises(ForbiddenError):
            svc.answer(session_id, 1, "accept", PUBLIC)
        svc.answer(session_id, 1, "cancel", PUBLIC)
        release.set()
        await svc.wait_pairings()

    async def test_answering_an_unknown_session_is_404(self, svc):
        with pytest.raises(NotFoundError):
            svc.answer("gibt-es-nicht", 1, "cancel", LAN)


class TestScan:
    async def test_the_window_is_reused_and_closes_by_itself(self, backend):
        short = BluetoothService(backend=backend, scan_seconds=0.05)
        try:
            first = await short.start_scan()
            assert await short.start_scan() == first
            names = {d.name for d in (await short.get_state(LAN)).devices}
            assert "Dev-Maus" in names
            await asyncio.sleep(0.15)
            assert "Dev-Maus" not in {d.name for d in (await short.get_state(LAN)).devices}
        finally:
            await short.aclose()

    async def test_scanning_with_the_adapter_off_is_409(self, svc):
        await svc.set_powered(False)
        with pytest.raises(ConflictError):
            await svc.start_scan()


class TestActions:
    async def test_connect_when_already_connected_is_fine(self, backend, svc):
        async def already(path):
            raise BlueZError("org.bluez.Error.AlreadyConnected", "")
        backend.connect = already
        await svc.connect("AA:AA:AA:AA:AA:02")

    async def test_raw_bluez_text_never_reaches_the_error_message(self, backend, svc):
        async def chatty(path):
            raise BlueZError("org.bluez.Error.Failed", "/var/lib/bluetooth/geheim")
        backend.connect = chatty
        with pytest.raises(BadGatewayError) as info:
            await svc.connect("AA:AA:AA:AA:AA:03")
        assert "geheim" not in info.value.public_message

    async def test_remove_returns_the_removed_device(self, svc):
        device = await svc.remove("AA:AA:AA:AA:AA:03")
        assert device.name == "JBL TUNE510BT"
        assert "JBL TUNE510BT" not in {d.name for d in (await svc.get_state(LAN)).devices}
