"""Die EINZIGE Stelle, die ``org.bluez`` kennt.

Oben reine Funktionen (ohne Bus testbar), darunter ab Task 4 der duenne
Client ueber dem System-Bus. ``parse_objects`` erwartet die bereits per
``unwrap`` entpackte Ausgabe von ``GetManagedObjects``.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional, Sequence

try:
    from dbus_next import BusType, Message, MessageType, Variant
    from dbus_next.aio import MessageBus
    _DBUS_AVAILABLE = True
except ImportError:  # pragma: no cover — dbus-next ist Abhaengigkeit, nur Rueckfall
    BusType = Message = MessageType = Variant = MessageBus = None  # type: ignore[assignment,misc]
    _DBUS_AVAILABLE = False

logger = logging.getLogger(__name__)

BLUEZ = "org.bluez"
ADAPTER_IFACE = "org.bluez.Adapter1"
DEVICE_IFACE = "org.bluez.Device1"
BATTERY_IFACE = "org.bluez.Battery1"

_MAC = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")
_INPUT_ICONS = frozenset({"input-keyboard", "input-mouse", "input-tablet"})


@dataclass(frozen=True)
class AdapterInfo:
    path: str
    address: str
    name: str
    powered: bool
    discovering: bool


@dataclass(frozen=True)
class DeviceInfo:
    path: str
    adapter_path: str
    address: str
    name: str
    icon: Optional[str]
    paired: bool
    trusted: bool
    connected: bool
    battery_percent: Optional[int]
    rssi: Optional[int]


@dataclass(frozen=True)
class Snapshot:
    adapters: tuple[AdapterInfo, ...]
    devices: tuple[DeviceInfo, ...]


def unwrap(value: Any) -> Any:
    """Loest dbus-next-Variants rekursiv auf; ``ay`` wird zu Hex."""
    if Variant is not None and isinstance(value, Variant):
        return unwrap(value.value)
    if isinstance(value, dict):
        return {str(k): unwrap(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [unwrap(v) for v in value]
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    return value


def normalize_address(raw: str) -> Optional[str]:
    """Liefert die MAC grossgeschrieben oder ``None``, wenn sie keine ist."""
    text = (raw or "").strip().upper()
    return text if _MAC.match(text) else None


def device_path(adapter_path: str, address: str) -> str:
    """Baut den Objektpfad aus einer bereits GEPRUEFTEN Adresse."""
    return f"{adapter_path}/dev_{address.replace(':', '_')}"


def kind_for_icon(icon: Optional[str]) -> str:
    """Ordnet das von BlueZ gemeldete Icon einer UI-Gruppe zu.

    ``Icon`` meldet das Geraet selbst — die Gruppe ist Anzeige, keine
    Sicherheitsaussage (siehe Spec, Sicherheit Punkt 7).
    """
    if not icon:
        return "other"
    if icon == "input-gaming":
        return "controller"
    if icon.startswith("audio-"):
        return "audio"
    if icon in _INPUT_ICONS:
        return "input"
    return "other"


def _opt_int(value: Any) -> Optional[int]:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def parse_objects(objects: dict) -> Snapshot:
    """Macht aus dem entpackten Objektbaum Adapter- und Geraeteliste."""
    adapters: list[AdapterInfo] = []
    devices: list[DeviceInfo] = []
    for path in sorted(objects):
        ifaces = objects[path] or {}
        adapter = ifaces.get(ADAPTER_IFACE)
        if adapter is not None:
            adapters.append(AdapterInfo(
                path=path,
                address=str(adapter.get("Address", "")).upper(),
                name=str(adapter.get("Alias") or adapter.get("Name") or ""),
                powered=bool(adapter.get("Powered", False)),
                discovering=bool(adapter.get("Discovering", False)),
            ))
        device = ifaces.get(DEVICE_IFACE)
        if device is None:
            continue
        address = normalize_address(str(device.get("Address", "")))
        if address is None:
            continue
        battery = ifaces.get(BATTERY_IFACE) or {}
        devices.append(DeviceInfo(
            path=path,
            adapter_path=str(device.get("Adapter", "")),
            address=address,
            name=str(device.get("Alias") or device.get("Name") or address),
            icon=device.get("Icon") or None,
            paired=bool(device.get("Paired", False)),
            trusted=bool(device.get("Trusted", False)),
            connected=bool(device.get("Connected", False)),
            battery_percent=_opt_int(battery.get("Percentage")),
            rssi=_opt_int(device.get("RSSI")),
        ))
    return Snapshot(adapters=tuple(adapters), devices=tuple(devices))


def select_adapter(
    adapters: Sequence[AdapterInfo], configured: str,
) -> tuple[Optional[AdapterInfo], Optional[str], Optional[str]]:
    """Waehlt den Adapter — nie stilles Umschwenken.

    Returns:
        (adapter, detail, warning). ``adapter`` ist ``None``, wenn nicht
        eindeutig entschieden werden kann; ``detail`` sagt dann, warum.
    """
    wanted = (configured or "").strip().upper()
    if wanted:
        match = next((a for a in adapters if a.address.upper() == wanted), None)
        if match is None:
            return None, f"Adapter {wanted} nicht vorhanden", None
        warning = "Mehrere Bluetooth-Adapter erkannt" if len(adapters) > 1 else None
        return match, None, warning
    if not adapters:
        return None, "Kein Bluetooth-Adapter gefunden", None
    if len(adapters) > 1:
        return None, "Mehrere Bluetooth-Adapter — BLUETOOTH_ADAPTER_ADDRESS setzen", None
    return adapters[0], None, None


# --- Bus-Client --------------------------------------------------------------

CALL_TIMEOUT_SECONDS = 10.0
PROPERTIES_IFACE = "org.freedesktop.DBus.Properties"
OBJECT_MANAGER_IFACE = "org.freedesktop.DBus.ObjectManager"
TIMEOUT_ERROR = "org.baluhost.Error.Timeout"
BUS_ERROR = "org.baluhost.Error.BusUnavailable"


class BlueZError(Exception):
    """Ein Fehler von BlueZ oder vom Bus, mit dem D-Bus-Fehlernamen.

    ``text`` stammt roh von BlueZ. Er wird geloggt, aber NIE an einen Client
    ausgeliefert — die Route bildet ``name`` auf kuratierte Meldungen ab.
    """

    def __init__(self, name: str, text: str = "") -> None:
        super().__init__(f"{name}: {text}" if text else name)
        self.name = name
        self.text = text


async def _connect_system_bus() -> Any:
    if not _DBUS_AVAILABLE:
        raise BlueZError(BUS_ERROR, "dbus-next nicht verfuegbar")
    return await MessageBus(bus_type=BusType.SYSTEM).connect()


class BlueZClient:
    """Eine Bus-Verbindung pro Worker, bei Bedarf und nach Fehlern neu aufgebaut."""

    def __init__(self, bus_factory: Optional[Callable[[], Awaitable[Any]]] = None) -> None:
        self._factory = bus_factory or _connect_system_bus
        self._bus: Any = None
        self._lock = asyncio.Lock()

    async def _get_bus(self) -> Any:
        async with self._lock:
            if self._bus is None or not getattr(self._bus, "connected", True):
                try:
                    self._bus = await self._factory()
                except BlueZError:
                    raise
                except Exception as exc:
                    raise BlueZError(BUS_ERROR, type(exc).__name__) from exc
            return self._bus

    async def call(
        self,
        path: str,
        interface: str,
        member: str,
        signature: str = "",
        body: Optional[Sequence[Any]] = None,
        timeout: Optional[float] = CALL_TIMEOUT_SECONDS,
    ) -> list:
        """Ruft eine Methode an ``org.bluez`` und liefert den Antwort-Rumpf."""
        bus = await self._get_bus()
        msg = Message(
            destination=BLUEZ, path=path, interface=interface, member=member,
            signature=signature, body=list(body or []),
        )
        try:
            pending = bus.call(msg)
            reply = await (asyncio.wait_for(pending, timeout) if timeout is not None else pending)
        except asyncio.TimeoutError as exc:
            raise BlueZError(TIMEOUT_ERROR, member) from exc
        except (OSError, EOFError) as exc:
            self._bus = None
            raise BlueZError(BUS_ERROR, type(exc).__name__) from exc
        if reply.message_type == MessageType.ERROR:
            text = reply.body[0] if reply.body else ""
            raise BlueZError(reply.error_name or "org.bluez.Error.Failed", str(text))
        return list(reply.body or [])

    async def get_managed_objects(self) -> dict:
        body = await self.call("/", OBJECT_MANAGER_IFACE, "GetManagedObjects")
        return unwrap(body[0]) if body else {}

    async def set_property(
        self, path: str, interface: str, name: str, signature: str, value: Any,
    ) -> None:
        await self.call(
            path, PROPERTIES_IFACE, "Set", "ssv", [interface, name, Variant(signature, value)],
        )

    async def export(self, path: str, interface_obj: Any) -> None:
        bus = await self._get_bus()
        bus.export(path, interface_obj)

    def unexport(self, path: str) -> None:
        if self._bus is not None:
            self._bus.unexport(path)
