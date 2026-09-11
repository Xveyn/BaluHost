"""Bluetooth-Backends: ein Protokoll, eine Attrappe, eine echte Umsetzung.

Aufbau wie ``audio_control/backend.py``. Beide Backends werfen ``BlueZError``
mit echten BlueZ-Fehlernamen, damit die Fehlerabbildung im Service fuer Dev
und Produktion dieselbe ist.
"""
from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass
from typing import Dict, Optional, Protocol

from app.plugins.installed.bluetooth.agent import AGENT_CAPABILITY, AGENT_PATH, BluezAgent
from app.plugins.installed.bluetooth.bluez import (
    ADAPTER_IFACE,
    CALL_TIMEOUT_SECONDS,
    DEVICE_IFACE,
    AdapterInfo,
    BlueZClient,
    BlueZError,
    DeviceInfo,
    Snapshot,
    device_path,
    parse_objects,
)
from app.plugins.installed.bluetooth.pairing import PairingPrompter

try:
    from dbus_next import Variant
except ImportError:  # pragma: no cover
    Variant = None  # type: ignore[assignment,misc]

CONNECT_TIMEOUT_SECONDS = 30.0
AGENT_MANAGER_PATH = "/org/bluez"
AGENT_MANAGER_IFACE = "org.bluez.AgentManager1"
DEV_ADAPTER_PATH = "/org/bluez/hci0"


class BluetoothBackend(Protocol):
    async def snapshot(self) -> Snapshot: ...
    async def set_powered(self, adapter_path: str, powered: bool) -> None: ...
    async def start_scan(self, adapter_path: str) -> None: ...
    async def stop_scan(self, adapter_path: str) -> None: ...
    async def connect(self, device_path: str) -> None: ...
    async def disconnect(self, device_path: str) -> None: ...
    async def remove(self, adapter_path: str, device_path: str) -> None: ...
    async def pair(self, device_path: str, prompter: PairingPrompter) -> None: ...
    async def set_trusted(self, device_path: str, trusted: bool) -> None: ...
    async def cancel_pairing(self, device_path: str) -> None: ...


@dataclass
class _DevDevice:
    address: str
    name: str
    icon: str
    flow: str  # "none" | "passkey" | "confirm"
    paired: bool = False
    trusted: bool = False
    connected: bool = False
    battery: Optional[int] = None


def _dev_paired() -> list[_DevDevice]:
    return [
        _DevDevice("AA:AA:AA:AA:AA:02", "Xbox Wireless Controller", "input-gaming", "none",
                   paired=True, trusted=True, connected=True, battery=80),
        _DevDevice("AA:AA:AA:AA:AA:03", "JBL TUNE510BT", "audio-headphones", "none",
                   paired=True, trusted=True),
    ]


def _dev_found() -> list[_DevDevice]:
    return [
        _DevDevice("AA:AA:AA:AA:AA:04", "Dev-Tastatur", "input-keyboard", "passkey"),
        _DevDevice("AA:AA:AA:AA:AA:05", "Dev-Maus", "input-mouse", "none"),
        _DevDevice("AA:AA:AA:AA:AA:06", "Dev-Telefon", "phone", "confirm"),
    ]


class DevBluetoothBackend:
    """Zustand im Speicher, damit jeder UI-Pfad auf Windows bedienbar ist."""

    def __init__(self, step_seconds: float = 1.0, passkey: Optional[int] = None) -> None:
        self._step = step_seconds
        self._passkey = passkey
        self._powered = True
        self._discovering = False
        self._devices: Dict[str, _DevDevice] = {
            device_path(DEV_ADAPTER_PATH, d.address): d for d in _dev_paired()
        }
        self._cancelled: set[str] = set()

    def _get(self, path: str) -> _DevDevice:
        device = self._devices.get(path)
        if device is None:
            raise BlueZError("org.bluez.Error.DoesNotExist", "Dev: unbekanntes Geraet")
        return device

    def _require_powered(self) -> None:
        if not self._powered:
            raise BlueZError("org.bluez.Error.NotReady", "Dev: Adapter aus")

    async def snapshot(self) -> Snapshot:
        adapter = AdapterInfo(
            path=DEV_ADAPTER_PATH, address="AA:AA:AA:AA:AA:01", name="BaluNode (Dev)",
            powered=self._powered, discovering=self._discovering,
        )
        devices = tuple(
            DeviceInfo(
                path=path, adapter_path=DEV_ADAPTER_PATH, address=d.address, name=d.name,
                icon=d.icon, paired=d.paired, trusted=d.trusted, connected=d.connected,
                battery_percent=d.battery if d.connected else None,
                rssi=None if d.paired else -55,
            )
            for path, d in sorted(self._devices.items())
        )
        return Snapshot(adapters=(adapter,), devices=devices)

    async def set_powered(self, adapter_path: str, powered: bool) -> None:
        self._powered = powered
        if not powered:
            self._discovering = False
            for device in self._devices.values():
                device.connected = False

    async def start_scan(self, adapter_path: str) -> None:
        self._require_powered()
        self._discovering = True
        for device in _dev_found():
            self._devices.setdefault(device_path(DEV_ADAPTER_PATH, device.address), device)

    async def stop_scan(self, adapter_path: str) -> None:
        self._discovering = False
        self._devices = {p: d for p, d in self._devices.items() if d.paired}

    async def connect(self, device_path: str) -> None:
        self._require_powered()
        device = self._get(device_path)
        if not device.paired:
            raise BlueZError("org.bluez.Error.Failed", "Dev: nicht gekoppelt")
        device.connected = True

    async def disconnect(self, device_path: str) -> None:
        self._get(device_path).connected = False

    async def remove(self, adapter_path: str, device_path: str) -> None:
        self._get(device_path)
        del self._devices[device_path]

    async def pair(self, device_path: str, prompter: PairingPrompter) -> None:
        self._require_powered()
        device = self._get(device_path)
        if device.paired:
            raise BlueZError("org.bluez.Error.AlreadyExists", "Dev: schon gekoppelt")
        self._cancelled.discard(device_path)
        key = self._passkey if self._passkey is not None else secrets.randbelow(10**6)
        if device.flow == "passkey":
            for entered in range(7):
                self._raise_if_cancelled(device_path)
                prompter.show_passkey(key, entered)
                await asyncio.sleep(self._step)
        elif device.flow == "confirm":
            accepted = await prompter.ask_confirmation(key)
            self._raise_if_cancelled(device_path)
            if not accepted:
                raise BlueZError("org.bluez.Error.AuthenticationRejected", "Dev: abgelehnt")
        else:
            await asyncio.sleep(self._step)
        self._raise_if_cancelled(device_path)
        device.paired = True

    def _raise_if_cancelled(self, device_path: str) -> None:
        if device_path in self._cancelled:
            raise BlueZError("org.bluez.Error.AuthenticationCanceled", "Dev: abgebrochen")

    async def set_trusted(self, device_path: str, trusted: bool) -> None:
        self._get(device_path).trusted = trusted

    async def cancel_pairing(self, device_path: str) -> None:
        self._cancelled.add(device_path)


class BlueZBackend:
    """Spricht ueber ``BlueZClient`` mit dem echten BlueZ auf dem System-Bus.

    Der Dienst-User muss in der Gruppe ``bluetooth`` sein (D-Bus-Policy von
    BlueZ); auf BaluNode gemessen, kein sudo.
    """

    def __init__(self, client: Optional[BlueZClient] = None) -> None:
        self._client = client or BlueZClient()

    async def snapshot(self) -> Snapshot:
        return parse_objects(await self._client.get_managed_objects())

    async def set_powered(self, adapter_path: str, powered: bool) -> None:
        await self._client.set_property(adapter_path, ADAPTER_IFACE, "Powered", "b", powered)

    async def start_scan(self, adapter_path: str) -> None:
        await self._client.call(
            adapter_path, ADAPTER_IFACE, "SetDiscoveryFilter", "a{sv}",
            [{"Transport": Variant("s", "auto")}],
        )
        await self._client.call(adapter_path, ADAPTER_IFACE, "StartDiscovery")

    async def stop_scan(self, adapter_path: str) -> None:
        await self._client.call(adapter_path, ADAPTER_IFACE, "StopDiscovery")

    async def connect(self, device_path: str) -> None:
        await self._client.call(device_path, DEVICE_IFACE, "Connect", timeout=CONNECT_TIMEOUT_SECONDS)

    async def disconnect(self, device_path: str) -> None:
        await self._client.call(device_path, DEVICE_IFACE, "Disconnect", timeout=CONNECT_TIMEOUT_SECONDS)

    async def remove(self, adapter_path: str, device_path: str) -> None:
        await self._client.call(
            adapter_path, ADAPTER_IFACE, "RemoveDevice", "o", [device_path],
            timeout=CALL_TIMEOUT_SECONDS,
        )

    async def pair(self, device_path: str, prompter: PairingPrompter) -> None:
        """Meldet den Agenten an, koppelt und meldet ihn in JEDEM Fall wieder ab.

        Kein ``RequestDefaultAgent``: dieser Agent bedient nur Kopplungen,
        die diese Verbindung selbst anstoesst. Das Zeitlimit setzt der
        Koordinator (``timeout=None`` hier).
        """
        await self._client.export(AGENT_PATH, BluezAgent(prompter))
        try:
            await self._client.call(
                AGENT_MANAGER_PATH, AGENT_MANAGER_IFACE, "RegisterAgent", "os",
                [AGENT_PATH, AGENT_CAPABILITY],
            )
            try:
                await self._client.call(device_path, DEVICE_IFACE, "Pair", timeout=None)
            finally:
                try:
                    await self._client.call(
                        AGENT_MANAGER_PATH, AGENT_MANAGER_IFACE, "UnregisterAgent", "o", [AGENT_PATH],
                    )
                except BlueZError:
                    pass
        finally:
            self._client.unexport(AGENT_PATH)

    async def set_trusted(self, device_path: str, trusted: bool) -> None:
        await self._client.set_property(device_path, DEVICE_IFACE, "Trusted", "b", trusted)

    async def cancel_pairing(self, device_path: str) -> None:
        await self._client.call(device_path, DEVICE_IFACE, "CancelPairing")
