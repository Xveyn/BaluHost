"""Koppel-Sitzung: systemweit hoechstens eine, gehalten von EINEM Worker.

Der Worker, der ``POST /pair`` annimmt, wird Besitzer: er haelt die
Dateisperre, laesst den Agenten auf SEINER Bus-Verbindung laufen und
schreibt den Stand nach ``/dev/shm/baluhost/bluetooth_pairing.json``. Die
UI-Abfragen landen auf beliebigen Workern und lesen nur diese Datei. Der
Rueckweg (Ja/Nein, Abbruch) laeuft ueber eine zweite Datei, die der Besitzer
abfragt.

Die Sperre liegt BEWUSST nicht im SHM-Verzeichnis: ``cleanup_shm()``
(``services/monitoring/shm.py``) loescht dort beim Beenden des
Monitoring-Workers alle Dateien. Eine geloeschte, aber noch gesperrte Datei
liesse einen zweiten Worker eine neue anlegen und sperren — zwei
gleichzeitige Kopplungen. ``/tmp`` ist durch ``PrivateTmp`` pro Unit privat,
aber zwischen den vier Workern derselben Unit geteilt.

Code und PIN werden hier nie geloggt.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, Protocol

from app.plugins.installed.bluetooth.bluez import BlueZError, DeviceInfo
from app.plugins.installed.bluetooth.models import PairingSession
from app.services.monitoring import shm

logger = logging.getLogger(__name__)

STATUS_FILE = "bluetooth_pairing.json"
ANSWER_FILE = "bluetooth_pairing_answer.json"
LOCK_PATH = (
    Path(tempfile.gettempdir()) / "baluhost-bluetooth-pairing.lock"
    if sys.platform == "win32"
    else Path("/tmp/baluhost-bluetooth-pairing.lock")
)
PAIR_TIMEOUT_SECONDS = 60.0
HEARTBEAT_SECONDS = 5.0
STALE_AFTER_SECONDS = 15.0
ANSWER_POLL_SECONDS = 0.25
RESULT_DISPLAY_SECONDS = 10.0
TERMINAL_STAGES = frozenset({"succeeded", "failed", "cancelled"})

_UNREACHABLE = frozenset({
    "org.bluez.Error.AuthenticationTimeout",
    "org.bluez.Error.ConnectionAttemptFailed",
    "org.baluhost.Error.Timeout",
})


class PairingPrompter(Protocol):
    """Was der Agent waehrend einer Kopplung braucht."""

    device_path: str
    device_icon: Optional[str]

    def show_passkey(self, passkey: int, entered: int) -> None: ...
    def show_pin(self, pin: str) -> None: ...
    async def ask_confirmation(self, passkey: int) -> bool: ...
    def cancelled(self) -> None: ...


class PairBackend(Protocol):
    async def pair(self, device_path: str, prompter: PairingPrompter) -> None: ...
    async def set_trusted(self, device_path: str, trusted: bool) -> None: ...
    async def connect(self, device_path: str) -> None: ...
    async def cancel_pairing(self, device_path: str) -> None: ...


OnFinished = Callable[[str, Optional[str]], None]


class PairingBusy(Exception):
    """Eine andere Kopplung haelt die Sperre."""


class PairingLock:
    """OS-Dateisperre fuer die Dauer einer Sitzung.

    Der Kernel gibt ``flock`` frei, wenn der Prozess stirbt — die Sperre
    braucht deshalb kein Ablaufdatum und kann nicht verwaisen.
    """

    def __init__(self) -> None:
        self._fd: Optional[int] = None

    def acquire(self) -> bool:
        path = LOCK_PATH  # zur Aufrufzeit gelesen (Tests biegen den Pfad um)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            if sys.platform == "win32":
                import msvcrt
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            return False
        self._fd = fd
        return True

    def release(self) -> None:
        if self._fd is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt
                try:
                    os.lseek(self._fd, 0, os.SEEK_SET)
                    msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                import fcntl
                fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            os.close(self._fd)
            self._fd = None


def outcome_for_error(exc: BlueZError) -> tuple[str, Optional[str]]:
    """Bildet einen BlueZ-Fehler auf (stage, kuratierter Fehlerschluessel) ab."""
    if exc.name == "org.bluez.Error.AlreadyExists":
        return "succeeded", None
    if exc.name == "org.bluez.Error.AuthenticationFailed":
        return "failed", "auth_failed"
    if exc.name in ("org.bluez.Error.AuthenticationCanceled", "org.bluez.Error.AuthenticationRejected"):
        return "cancelled", None
    if exc.name in _UNREACHABLE or (exc.name == "org.bluez.Error.Failed" and "timeout" in exc.text):
        return "failed", "unreachable"
    return "failed", "unknown"


def _read_status() -> Optional[dict]:
    return shm.read_shm(STATUS_FILE, max_age_seconds=STALE_AFTER_SECONDS)


def _delete(filename: str) -> None:
    try:
        (shm.SHM_DIR / filename).unlink()
    except OSError:
        pass


def read_session_for(user_id: int) -> Optional[PairingSession]:
    """Liefert die Sitzung NUR dem Initiator; allen anderen ``None``."""
    raw = _read_status()
    if not raw or raw.get("user_id") != user_id:
        return None
    return PairingSession(**{key: raw.get(key) for key in PairingSession.model_fields})


def pairing_active() -> bool:
    raw = _read_status()
    return bool(raw) and raw.get("stage") not in TERMINAL_STAGES


def write_answer(session_id: str, user_id: int, action: str) -> bool:
    """Legt eine Antwort fuer den Besitzer ab — nur fuer die eigene Sitzung."""
    raw = _read_status()
    if not raw or raw.get("session_id") != session_id or raw.get("user_id") != user_id:
        return False
    shm.write_shm(ANSWER_FILE, {
        "session_id": session_id, "user_id": user_id, "action": action, "at": time.time(),
    })
    return True


def _take_answer(session_id: str) -> Optional[str]:
    target = shm.SHM_DIR / ANSWER_FILE
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    _delete(ANSWER_FILE)
    if data.get("session_id") != session_id:
        return None
    return data.get("action")


class ActivePairing:
    """Laufzeit-Zustand im Besitzer-Worker; zugleich der Prompter des Agenten."""

    def __init__(self, session_id: str, user_id: int, device: DeviceInfo) -> None:
        self.session_id = session_id
        self.user_id = user_id
        self.device = device
        self.device_path = device.path
        self.device_icon = device.icon
        self.stage = "connecting"
        self.code: Optional[str] = None
        self.entered: Optional[int] = None
        self.error: Optional[str] = None
        self.cancel_requested = False
        self._confirm: Optional[asyncio.Future] = None

    def publish(self) -> None:
        shm.write_shm(STATUS_FILE, {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "address": self.device.address,
            "device_name": self.device.name,
            "stage": self.stage,
            "code": self.code,
            "entered": self.entered,
            "error": self.error,
            "updated_at": time.time(),
        })

    def show_passkey(self, passkey: int, entered: int) -> None:
        self.stage, self.code, self.entered = "display_passkey", f"{passkey:06d}", entered
        self.publish()

    def show_pin(self, pin: str) -> None:
        self.stage, self.code, self.entered = "display_pin", pin, None
        self.publish()

    async def ask_confirmation(self, passkey: int) -> bool:
        self.stage, self.code, self.entered = "confirm", f"{passkey:06d}", None
        self.publish()
        self._confirm = asyncio.get_running_loop().create_future()
        try:
            return await asyncio.wait_for(asyncio.shield(self._confirm), PAIR_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            return False
        finally:
            self._confirm = None

    def resolve_confirmation(self, accept: bool) -> None:
        if self._confirm is not None and not self._confirm.done():
            self._confirm.set_result(accept)

    def cancelled(self) -> None:
        self.resolve_confirmation(False)

    def finish(self, stage: str, error: Optional[str]) -> None:
        # Code und Fortschritt verschwinden mit dem Ende — sie sollen nicht
        # noch zehn Sekunden in der Datei stehen.
        self.stage, self.code, self.entered, self.error = stage, None, None, error
        self.publish()


async def _quietly(action: Awaitable[Any], what: str) -> None:
    try:
        await action
    except BlueZError as exc:
        logger.warning("Bluetooth: %s fehlgeschlagen (%s)", what, exc.name)


class PairingCoordinator:
    """Startet und begleitet Kopplungen dieses Workers."""

    def __init__(self) -> None:
        self._runs: set[asyncio.Task] = set()
        self._cleanups: set[asyncio.Task] = set()

    def start(self, backend: PairBackend, device: DeviceInfo, user_id: int,
              on_finished: OnFinished) -> str:
        lock = PairingLock()
        if not lock.acquire():
            raise PairingBusy()
        session_id = secrets.token_urlsafe(16)
        active = ActivePairing(session_id, user_id, device)
        _delete(ANSWER_FILE)
        active.publish()
        task = asyncio.create_task(self._run(backend, active, lock, on_finished))
        self._runs.add(task)
        task.add_done_callback(self._runs.discard)
        return session_id

    async def _run(self, backend: PairBackend, active: ActivePairing, lock: PairingLock,
                   on_finished: OnFinished) -> None:
        heartbeat = asyncio.create_task(self._heartbeat(active))
        answers = asyncio.create_task(self._watch_answers(backend, active))
        stage, error = "failed", "unknown"
        try:
            try:
                await asyncio.wait_for(backend.pair(active.device_path, active), PAIR_TIMEOUT_SECONDS)
                stage, error = "succeeded", None
            except asyncio.TimeoutError:
                await _quietly(backend.cancel_pairing(active.device_path), "CancelPairing")
                stage, error = "failed", "timeout"
            except BlueZError as exc:
                logger.info("Bluetooth: Kopplung mit %s endete mit %s", active.device.address, exc.name)
                stage, error = outcome_for_error(exc)
            if active.cancel_requested and stage != "succeeded":
                stage, error = "cancelled", None
            if stage == "succeeded":
                # Trusted ist noetig, damit Controller und Eingabegeraete nach
                # dem Aufwachen selbst wieder verbinden.
                await _quietly(backend.set_trusted(active.device_path, True), "Trusted")
                await _quietly(backend.connect(active.device_path), "Connect")
        except Exception:
            logger.exception("Bluetooth: unerwarteter Fehler in der Kopplung")
            stage, error = "failed", "unknown"
        finally:
            heartbeat.cancel()
            answers.cancel()
            active.finish(stage, error)
            lock.release()
            try:
                on_finished(stage, error)
            except Exception:
                logger.exception("Bluetooth: on_finished fehlgeschlagen")
            cleanup = asyncio.create_task(self._expire(active.session_id))
            self._cleanups.add(cleanup)
            cleanup.add_done_callback(self._cleanups.discard)

    async def _heartbeat(self, active: ActivePairing) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_SECONDS)
            active.publish()

    async def _watch_answers(self, backend: PairBackend, active: ActivePairing) -> None:
        while True:
            await asyncio.sleep(ANSWER_POLL_SECONDS)
            action = _take_answer(active.session_id)
            if action == "cancel":
                active.cancel_requested = True
                active.resolve_confirmation(False)
                await _quietly(backend.cancel_pairing(active.device_path), "CancelPairing")
            elif action in ("accept", "reject"):
                active.resolve_confirmation(action == "accept")

    async def _expire(self, session_id: str) -> None:
        await asyncio.sleep(RESULT_DISPLAY_SECONDS)
        raw = shm.read_shm(STATUS_FILE, max_age_seconds=3600)
        if raw and raw.get("session_id") == session_id:
            _delete(STATUS_FILE)

    async def wait_idle(self) -> None:
        """Wartet, bis alle laufenden Kopplungen dieses Workers beendet sind."""
        if self._runs:
            await asyncio.gather(*list(self._runs), return_exceptions=True)

    async def aclose(self) -> None:
        """Bricht Aufraeum-Tasks ab (Shutdown und Tests)."""
        for task in list(self._runs) + list(self._cleanups):
            task.cancel()
        await asyncio.gather(*list(self._runs), *list(self._cleanups), return_exceptions=True)
