"""Pydantic-Modelle der Bluetooth-Steuerung.

Die Feldnamen sind der API-Vertrag zum Frontend (``client/src/api/bluetooth.ts``).
Kein BlueZ-Rohtyp (ManufacturerData, AdvertisingData, UUIDs) erscheint hier —
die Modelle uebernehmen nur, was die UI braucht.
"""
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

DeviceKind = Literal["controller", "audio", "input", "other"]

PairingStage = Literal[
    "connecting",
    "display_passkey",
    "display_pin",
    "confirm",
    "succeeded",
    "failed",
    "cancelled",
]


class BluetoothAdapter(BaseModel):
    address: str
    name: str
    powered: bool
    discovering: bool  # auch True, wenn KDE gerade scannt


class BluetoothDevice(BaseModel):
    address: str
    name: str
    kind: DeviceKind
    icon: Optional[str] = None
    paired: bool
    trusted: bool
    connected: bool
    battery_percent: Optional[int] = None
    rssi: Optional[int] = None


class BluetoothState(BaseModel):
    available: bool
    detail: Optional[str] = None
    warning: Optional[str] = None
    adapter: Optional[BluetoothAdapter] = None
    devices: List[BluetoothDevice] = Field(default_factory=list)
    can_pair_here: bool = False
    pairing_active: bool = False


class PairingSession(BaseModel):
    """Stand einer Kopplung — nur fuer den Initiator ausgeliefert."""

    session_id: str
    address: str
    device_name: str
    stage: PairingStage
    code: Optional[str] = None
    entered: Optional[int] = None
    error: Optional[str] = None  # kuratierter Schluessel, nie BlueZ-Rohtext


class PowerRequest(BaseModel):
    powered: bool


class ConfirmRequest(BaseModel):
    accept: bool


class ScanResponse(BaseModel):
    until: datetime


class PairStartResponse(BaseModel):
    session_id: str
