"""Dev-Backend (Zustand im Speicher) und BlueZ-Backend (Aufrufreihenfolge)."""
import asyncio

import pytest

from app.plugins.installed.bluetooth.backend import (
    DEV_ADAPTER_PATH,
    BlueZBackend,
    DevBluetoothBackend,
)
from app.plugins.installed.bluetooth.bluez import BlueZError, device_path

KEYBOARD = device_path(DEV_ADAPTER_PATH, "AA:AA:AA:AA:AA:04")
MOUSE = device_path(DEV_ADAPTER_PATH, "AA:AA:AA:AA:AA:05")
PHONE = device_path(DEV_ADAPTER_PATH, "AA:AA:AA:AA:AA:06")
XBOX = device_path(DEV_ADAPTER_PATH, "AA:AA:AA:AA:AA:02")


class _Prompter:
    def __init__(self, confirm=True):
        self.device_path = ""
        self.device_icon = None
        self.confirm = confirm
        self.passkeys = []

    def show_passkey(self, passkey, entered):
        self.passkeys.append((passkey, entered))

    def show_pin(self, pin):
        pass

    async def ask_confirmation(self, passkey):
        return self.confirm

    def cancelled(self):
        pass


def _names(snapshot):
    return {d.name for d in snapshot.devices}


class TestDevBackend:
    async def test_it_starts_with_the_two_paired_devices(self):
        snap = await DevBluetoothBackend(step_seconds=0).snapshot()
        assert len(snap.adapters) == 1
        assert all(d.paired for d in snap.devices)
        assert len(snap.devices) == 2

    async def test_a_scan_reveals_three_unpaired_devices_and_stop_drops_them(self):
        backend = DevBluetoothBackend(step_seconds=0)
        await backend.start_scan(DEV_ADAPTER_PATH)
        snap = await backend.snapshot()
        assert {"Dev-Tastatur", "Dev-Maus", "Dev-Telefon"} <= _names(snap)
        assert snap.adapters[0].discovering is True
        await backend.stop_scan(DEV_ADAPTER_PATH)
        assert "Dev-Maus" not in _names(await backend.snapshot())

    async def test_the_keyboard_shows_a_passkey_with_rising_progress(self):
        backend = DevBluetoothBackend(step_seconds=0, passkey=482913)
        await backend.start_scan(DEV_ADAPTER_PATH)
        prompter = _Prompter()
        await backend.pair(KEYBOARD, prompter)
        assert prompter.passkeys[0] == (482913, 0)
        assert prompter.passkeys[-1] == (482913, 6)
        paired = next(d for d in (await backend.snapshot()).devices if d.path == KEYBOARD)
        assert paired.paired is True

    async def test_a_refused_confirmation_raises_rejected(self):
        backend = DevBluetoothBackend(step_seconds=0)
        await backend.start_scan(DEV_ADAPTER_PATH)
        with pytest.raises(BlueZError) as info:
            await backend.pair(PHONE, _Prompter(confirm=False))
        assert info.value.name == "org.bluez.Error.AuthenticationRejected"

    async def test_pairing_a_paired_device_is_already_exists(self):
        with pytest.raises(BlueZError) as info:
            await DevBluetoothBackend(step_seconds=0).pair(XBOX, _Prompter())
        assert info.value.name == "org.bluez.Error.AlreadyExists"

    async def test_scanning_with_the_adapter_off_is_not_ready(self):
        backend = DevBluetoothBackend(step_seconds=0)
        await backend.set_powered(DEV_ADAPTER_PATH, False)
        with pytest.raises(BlueZError) as info:
            await backend.start_scan(DEV_ADAPTER_PATH)
        assert info.value.name == "org.bluez.Error.NotReady"

    async def test_connect_disconnect_remove(self):
        backend = DevBluetoothBackend(step_seconds=0)
        await backend.disconnect(XBOX)
        assert not next(d for d in (await backend.snapshot()).devices if d.path == XBOX).connected
        await backend.connect(XBOX)
        await backend.remove(DEV_ADAPTER_PATH, XBOX)
        assert XBOX not in {d.path for d in (await backend.snapshot()).devices}
        with pytest.raises(BlueZError) as info:
            await backend.remove(DEV_ADAPTER_PATH, XBOX)
        assert info.value.name == "org.bluez.Error.DoesNotExist"

    async def test_cancelling_mid_pairing_raises_cancelled_and_leaves_it_unpaired(self):
        backend = DevBluetoothBackend(step_seconds=0.05, passkey=482913)
        await backend.start_scan(DEV_ADAPTER_PATH)
        prompter = _Prompter()
        task = asyncio.create_task(backend.pair(KEYBOARD, prompter))
        while not prompter.passkeys:
            await asyncio.sleep(0.005)
        await backend.cancel_pairing(KEYBOARD)
        with pytest.raises(BlueZError) as info:
            await task
        assert info.value.name == "org.bluez.Error.AuthenticationCanceled"
        paired = next(d for d in (await backend.snapshot()).devices if d.path == KEYBOARD)
        assert paired.paired is False

    async def test_stop_scan_does_not_drop_an_in_flight_pairing(self):
        backend = DevBluetoothBackend(step_seconds=0.05, passkey=482913)
        await backend.start_scan(DEV_ADAPTER_PATH)
        prompter = _Prompter()
        task = asyncio.create_task(backend.pair(KEYBOARD, prompter))
        while not prompter.passkeys:
            await asyncio.sleep(0.005)
        await backend.stop_scan(DEV_ADAPTER_PATH)
        await task
        paired = next(d for d in (await backend.snapshot()).devices if d.path == KEYBOARD)
        assert paired.paired is True


class _RecordingClient:
    def __init__(self, fail_pair=None):
        self.calls = []
        self.fail_pair = fail_pair

    async def call(self, path, interface, member, signature="", body=None, timeout=10.0):
        self.calls.append((path, member, list(body or []), timeout))
        if member == "Pair" and self.fail_pair:
            raise BlueZError(self.fail_pair)
        return []

    async def set_property(self, path, interface, name, signature, value):
        self.calls.append((path, f"Set:{name}", [signature, value], None))

    async def export(self, path, interface_obj):
        self.calls.append((path, "export", [], None))

    def unexport(self, path):
        self.calls.append((path, "unexport", [], None))

    async def get_managed_objects(self):
        return {}


class TestBlueZBackend:
    async def test_pair_registers_the_agent_first_and_always_cleans_up(self):
        client = _RecordingClient(fail_pair="org.bluez.Error.AuthenticationFailed")
        with pytest.raises(BlueZError):
            await BlueZBackend(client).pair(KEYBOARD, _Prompter())
        members = [c[1] for c in client.calls]
        assert members == ["export", "RegisterAgent", "Pair", "UnregisterAgent", "unexport"]
        register = next(c for c in client.calls if c[1] == "RegisterAgent")
        assert register[2] == ["/org/baluhost/bluetooth/agent", "KeyboardDisplay"]
        pair = next(c for c in client.calls if c[1] == "Pair")
        assert pair[3] is None  # das Zeitlimit setzt der Koordinator

    async def test_no_default_agent_is_ever_requested(self):
        client = _RecordingClient()
        await BlueZBackend(client).pair(KEYBOARD, _Prompter())
        assert "RequestDefaultAgent" not in [c[1] for c in client.calls]

    async def test_scan_sets_the_filter_before_starting(self):
        client = _RecordingClient()
        await BlueZBackend(client).start_scan(DEV_ADAPTER_PATH)
        assert [c[1] for c in client.calls] == ["SetDiscoveryFilter", "StartDiscovery"]
        assert client.calls[0][2][0]["Transport"].value == "auto"

    async def test_power_and_trust_are_property_writes(self):
        client = _RecordingClient()
        backend = BlueZBackend(client)
        await backend.set_powered(DEV_ADAPTER_PATH, False)
        await backend.set_trusted(KEYBOARD, True)
        assert client.calls[0][1] == "Set:Powered" and client.calls[0][2] == ["b", False]
        assert client.calls[1][1] == "Set:Trusted" and client.calls[1][2] == ["b", True]

    async def test_remove_goes_through_the_adapter(self):
        client = _RecordingClient()
        await BlueZBackend(client).remove(DEV_ADAPTER_PATH, KEYBOARD)
        assert client.calls == [(DEV_ADAPTER_PATH, "RemoveDevice", [KEYBOARD], 10.0)]
