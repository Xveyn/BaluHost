"""Service-Schicht der Bluetooth-Steuerung.

Waehlt das Backend, haelt es als Singleton pro Worker und traegt die gesamte
Validierung: Keine Client-Zeichenkette erreicht BlueZ, bevor sie als MAC
geprueft und im aktuellen Objektbaum unter dem gebundenen Adapter gefunden
wurde. Objektpfade entstehen nur aus geprueften Adressen.

Fehler verlassen den Service ausschliesslich als ``ServiceError`` mit
kuratierter Meldung; BlueZ-Rohtext landet nur im Log.
"""
from __future__ import annotations

import asyncio
import logging
import platform
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional

from app.core.config import settings
from app.core.exceptions import (
    BadGatewayError,
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ServiceError,
)
from app.core.network_utils import is_private_or_local_ip
from app.plugins.installed.bluetooth import pairing
from app.plugins.installed.bluetooth.backend import (
    BluetoothBackend,
    BlueZBackend,
    DevBluetoothBackend,
)
from app.plugins.installed.bluetooth.bluez import (
    AdapterInfo,
    BlueZError,
    DeviceInfo,
    Snapshot,
    kind_for_icon,
    normalize_address,
    select_adapter,
)
from app.plugins.installed.bluetooth.models import (
    BluetoothAdapter,
    BluetoothDevice,
    BluetoothState,
    PairingSession,
)

logger = logging.getLogger(__name__)

SCAN_SECONDS = 30.0
DeviceFinished = Callable[[DeviceInfo, str, Optional[str]], None]

_service: Optional["BluetoothService"] = None


def action_error(exc: BlueZError) -> ServiceError:
    """Uebersetzt einen BlueZ-Fehler in eine kuratierte Antwort."""
    logger.warning("Bluetooth-Aktion fehlgeschlagen: %s %s", exc.name, exc.text)
    if exc.name in ("org.bluez.Error.DoesNotExist", "org.freedesktop.DBus.Error.UnknownObject"):
        return NotFoundError("Geraet nicht gefunden")
    if exc.name == "org.bluez.Error.InProgress":
        return ConflictError("Vorgang laeuft bereits")
    if exc.name == "org.bluez.Error.NotReady":
        return ConflictError("Adapter ist aus")
    if "timeout" in exc.text or exc.name == "org.baluhost.Error.Timeout":
        return BadGatewayError("Geraet nicht erreichbar — eingeschaltet?")
    return BadGatewayError("Bluetooth-Aktion fehlgeschlagen")


def _to_model(device: DeviceInfo) -> BluetoothDevice:
    return BluetoothDevice(
        address=device.address,
        name=device.name,
        kind=kind_for_icon(device.icon),
        icon=device.icon,
        paired=device.paired,
        trusted=device.trusted,
        connected=device.connected,
        battery_percent=device.battery_percent,
        rssi=device.rssi,
    )


class BluetoothService:
    """Duenne Huelle um das Backend, plus Validierung und Scan-Fenster."""

    def __init__(
        self,
        backend: Optional[BluetoothBackend] = None,
        coordinator: Optional[pairing.PairingCoordinator] = None,
        scan_seconds: float = SCAN_SECONDS,
    ) -> None:
        if backend is not None:
            self._backend: BluetoothBackend = backend
        elif getattr(settings, "is_dev_mode", False) or platform.system() != "Linux":
            # BlueZ gibt es auf Windows nicht, und im Dev-Modus soll nichts an
            # echten Funkgeraeten herumstellen.
            self._backend = DevBluetoothBackend()
        else:
            self._backend = BlueZBackend()
        self._coordinator = coordinator or pairing.PairingCoordinator()
        self._scan_seconds = scan_seconds
        self._scan_task: Optional[asyncio.Task] = None
        self._scan_until: Optional[datetime] = None

    # --- Lesen -----------------------------------------------------------

    async def get_state(self, client_host: Optional[str]) -> BluetoothState:
        """Liest den Zustand. Ein unerreichbares BlueZ ist kein Fehler, sondern
        ``available=false`` — die UI soll das anzeigen koennen."""
        common = {
            "can_pair_here": is_private_or_local_ip(client_host),
            "pairing_active": pairing.pairing_active(),
        }
        try:
            snapshot = await self._backend.snapshot()
        except BlueZError as exc:
            logger.warning("BlueZ nicht erreichbar: %s", exc.name)
            return BluetoothState(available=False, detail="Bluetooth-Dienst nicht erreichbar", **common)
        adapter, detail, warning = select_adapter(snapshot.adapters, settings.bluetooth_adapter_address)
        if adapter is None:
            return BluetoothState(available=False, detail=detail, **common)
        devices = [_to_model(d) for d in snapshot.devices if d.adapter_path == adapter.path]
        devices.sort(key=lambda d: (not d.paired, d.kind, d.name.lower()))
        return BluetoothState(
            available=True,
            warning=warning,
            adapter=BluetoothAdapter(
                address=adapter.address, name=adapter.name,
                powered=adapter.powered, discovering=adapter.discovering,
            ),
            devices=devices,
            **common,
        )

    async def _adapter(self) -> tuple[Snapshot, AdapterInfo]:
        try:
            snapshot = await self._backend.snapshot()
        except BlueZError as exc:
            raise BadGatewayError("Bluetooth nicht erreichbar") from exc
        adapter, detail, _ = select_adapter(snapshot.adapters, settings.bluetooth_adapter_address)
        if adapter is None:
            raise ConflictError(detail or "Kein Bluetooth-Adapter")
        return snapshot, adapter

    async def _device(self, address: str) -> tuple[AdapterInfo, DeviceInfo]:
        normalized = normalize_address(address)
        if normalized is None:
            raise BadRequestError("Ungueltige Geraeteadresse")
        snapshot, adapter = await self._adapter()
        device = next(
            (d for d in snapshot.devices if d.adapter_path == adapter.path and d.address == normalized),
            None,
        )
        if device is None:
            raise NotFoundError("Geraet nicht gefunden")
        return adapter, device

    async def _act(self, action: Awaitable[Any], ok_errors: frozenset = frozenset()) -> None:
        try:
            await action
        except BlueZError as exc:
            if exc.name in ok_errors:
                return
            raise action_error(exc) from exc

    # --- Aktionen --------------------------------------------------------

    async def set_powered(self, powered: bool) -> None:
        _, adapter = await self._adapter()
        await self._act(self._backend.set_powered(adapter.path, powered))

    async def start_scan(self) -> datetime:
        if self._scan_task is not None and not self._scan_task.done() and self._scan_until:
            return self._scan_until
        _, adapter = await self._adapter()
        if not adapter.powered:
            raise ConflictError("Adapter ist aus")
        await self._act(self._backend.start_scan(adapter.path))
        self._scan_until = datetime.now(timezone.utc) + timedelta(seconds=self._scan_seconds)
        self._scan_task = asyncio.create_task(self._stop_scan_later(adapter.path))
        return self._scan_until

    async def _stop_scan_later(self, adapter_path: str) -> None:
        await asyncio.sleep(self._scan_seconds)
        try:
            await self._backend.stop_scan(adapter_path)
        except BlueZError as exc:
            logger.info("Bluetooth: StopDiscovery ergab %s", exc.name)

    async def connect(self, address: str) -> None:
        _, device = await self._device(address)
        await self._act(self._backend.connect(device.path), frozenset({"org.bluez.Error.AlreadyConnected"}))

    async def disconnect(self, address: str) -> None:
        _, device = await self._device(address)
        await self._act(self._backend.disconnect(device.path), frozenset({"org.bluez.Error.NotConnected"}))

    async def remove(self, address: str) -> DeviceInfo:
        adapter, device = await self._device(address)
        await self._act(self._backend.remove(adapter.path, device.path))
        return device

    async def start_pairing(
        self, address: str, user_id: int, client_host: Optional[str], on_finished: DeviceFinished,
    ) -> str:
        """Prueft LAN, Adresse, Zustand — erst dann startet die Kopplung."""
        if not is_private_or_local_ip(client_host):
            raise ForbiddenError("Koppeln nur im lokalen Netz")
        adapter, device = await self._device(address)
        if device.paired:
            raise ConflictError("Geraet ist bereits gekoppelt")
        if not adapter.powered:
            raise ConflictError("Adapter ist aus")
        try:
            return self._coordinator.start(
                self._backend, device, user_id,
                lambda stage, error: on_finished(device, stage, error),
            )
        except pairing.PairingBusy as exc:
            raise ConflictError("Es wird bereits ein Geraet gekoppelt") from exc

    def pairing_status(self, user_id: int) -> Optional[PairingSession]:
        return pairing.read_session_for(user_id)

    def answer(self, session_id: str, user_id: int, action: str, client_host: Optional[str]) -> None:
        """Ja/Nein braucht das LAN (es schliesst eine Vertrauensentscheidung ab),
        Abbrechen nicht."""
        if action in ("accept", "reject") and not is_private_or_local_ip(client_host):
            raise ForbiddenError("Bestaetigen nur im lokalen Netz")
        if not pairing.write_answer(session_id, user_id, action):
            raise NotFoundError("Keine laufende Kopplung")

    async def wait_pairings(self) -> None:
        await self._coordinator.wait_idle()

    async def aclose(self) -> None:
        if self._scan_task is not None:
            self._scan_task.cancel()
        await self._coordinator.aclose()


def get_bluetooth_service() -> BluetoothService:
    """Liefert die Service-Instanz dieses Workers und legt sie beim ersten Aufruf an."""
    global _service
    if _service is None:
        _service = BluetoothService()
    return _service
