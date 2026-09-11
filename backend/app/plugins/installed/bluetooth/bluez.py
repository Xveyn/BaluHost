"""Die EINZIGE Stelle, die ``org.bluez`` kennt.

Oben reine Funktionen (ohne Bus testbar), darunter ab Task 4 der duenne
Client ueber dem System-Bus. ``parse_objects`` erwartet die bereits per
``unwrap`` entpackte Ausgabe von ``GetManagedObjects``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional, Sequence

try:
    from dbus_next import Variant
except ImportError:  # pragma: no cover — dbus-next ist Abhaengigkeit, nur Rueckfall
    Variant = None  # type: ignore[assignment,misc]

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
