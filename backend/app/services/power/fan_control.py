"""
Fan control service for PWM fan management.

Supports both Linux hardware (via hwmon sysfs) and development simulation.
Backend implementations are in fan_backend_dev.py and fan_backend_linux.py.
"""
import asyncio
import json
import logging
import time
import time as _time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Tuple

from sqlalchemy import select, desc, func, update
from sqlalchemy.exc import IntegrityError

from app.core import lifespan
from app.core.config import Settings
from app.models.fans import FanConfig, FanSample
from app.schemas.fans import FanMode, FanCurvePoint, PwmControl
from app.services.power.fan_restore import is_observation, needs_release, resolve_restore_value
from app.services.power.fan_ownership import (
    FanOwnership,
    is_released,
    ownership_after_release,
    should_release,
)
from app.services.power.fan_runtime_store import (
    publish_released_fans,
    read_denied_fans,
    read_released_fans,
    publish_write_permission,
    read_write_permission,
)
from app.services.power.fan_schedule import FanScheduleService
from app.services.power.fan_profiles import FanProfileService
from app.services.power.fan_reconcile import ChipFacts, reconcile_fan_identities
from app.services.power.fan_sources import (
    TempSourceRegistry, HwmonTempSource, GpuTempSource, DiskTempSource, MixTempSource,
)
from app.services.power.fan_curve_eval import evaluate_curve
from app.services.power.fan_gpu_acoustics import (
    find_fan_ctrl_dir,
    read_acoustics,
    write_acoustic,
)
from app.services.power.fan_gpu_acoustics_store import (
    AcousticsConfigError,
    capture_baseline,
    load_acoustics_config_fail_soft,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared data types
# ---------------------------------------------------------------------------

@dataclass
class FanData:
    """Current fan state data."""
    fan_id: str
    name: str
    rpm: Optional[int]
    pwm_percent: int
    temperature_celsius: Optional[float]
    mode: FanMode
    min_pwm_percent: int
    max_pwm_percent: int
    emergency_temp_celsius: float
    temp_sensor_id: Optional[str]
    curve_points: List[FanCurvePoint]
    is_active: bool
    hysteresis_celsius: float = 3.0
    # GPU recognition + write diagnostics
    is_gpu_fan: bool = False
    gpu_vendor: Optional[str] = None
    device_driver: Optional[str] = None
    last_write_error: Optional[str] = None
    pwm_control: PwmControl = PwmControl.SUPPORTED


@dataclass
class HysteresisState:
    """State for hysteresis tracking per fan."""
    last_pwm: int
    last_pwm_temp: float
    last_update: float


@dataclass
class TempSensorData:
    """Temperature sensor information."""
    sensor_id: str
    device_name: str
    label: Optional[str]
    is_cpu_sensor: bool
    current_temp: Optional[float]


# ---------------------------------------------------------------------------
# Backend ABC
# ---------------------------------------------------------------------------

class FanControlBackend(ABC):
    """Abstract base class for fan control backends."""

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if this backend is available on the system."""
        pass

    @abstractmethod
    async def get_fans(self) -> List[FanData]:
        """Get list of all available fans with current state."""
        pass

    @abstractmethod
    async def set_pwm(self, fan_id: str, pwm_percent: int, force: bool = False) -> bool:
        """
        Set PWM value for a fan.

        Args:
            fan_id: Fan identifier
            pwm_percent: PWM percentage (0-100)
            force: Ein etwaiges Backoff-Fenster uebergehen (#533). Fuer
                Nutzeraktionen und den Notfallpfad.

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def release_to_board(self, fan_id: str, enable_value: int) -> bool:
        """pwm_enable auf einen Automatikmodus zurueckschreiben (#534).

        Args:
            fan_id: Luefter-Kennung
            enable_value: der beobachtete Automatikmodus (>= 2)

        Returns:
            True nur, wenn der Wert danach tatsaechlich anliegt.
        """
        pass

    def clear_write_failures(self, fan_id: str) -> None:
        """Den Fehlerzaehler dieses Kanals zuruecksetzen (#534).

        Kein @abstractmethod, aus demselben Grund wie write_failure_state:
        ein Backend ohne Backoff hat nichts zurueckzusetzen.
        """
        return None

    def write_failure_state(self, fan_id: str) -> Tuple[int, bool]:
        """Wie oft der Regelkreis auf diesem Kanal nacheinander gescheitert ist.

        Returns:
            (fail_count, at_cap). `at_cap` heisst: das Backoff-Fenster steht am
            Maximum, der Kanal lehnt also seit acht aufeinanderfolgenden
            Versuchen ab.

        Kein @abstractmethod, sondern eine Vorgabe: ein Backend ohne Backoff
        (Dev) hat nie einen nicht steuerbaren Kanal, und ein neues Backend soll
        nicht an einer Methode scheitern, die nur die Rueckgabe-Entscheidung
        aus #534 braucht.
        """
        return 0, False

    @abstractmethod
    async def get_temperature(self, sensor_id: str) -> Optional[float]:
        """Get temperature reading from a sensor."""
        pass

    @abstractmethod
    async def get_available_temp_sensors(self) -> List[TempSensorData]:
        """List all available temperature sensors."""
        pass


# Re-export backend classes for backward compatibility
from app.services.power.fan_backend_dev import DevFanControlBackend  # noqa: E402
from app.services.power.fan_backend_linux import LinuxFanControlBackend  # noqa: E402


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class FanControlService:
    """Singleton service for managing fan control."""

    _instance: Optional["FanControlService"] = None
    _lock = asyncio.Lock()

    def __init__(self, config: Settings, db_session_factory):
        if FanControlService._instance is not None:
            raise RuntimeError("FanControlService already initialized. Use get_instance().")

        self.config = config
        self.db_session_factory = db_session_factory
        self._backend: Optional[FanControlBackend] = None
        self._monitoring_task: Optional[asyncio.Task] = None
        self._sample_buffer: deque = deque(maxlen=120)  # 10 minutes at 5s interval
        self._is_running = False
        self._use_linux_backend = False
        self._hysteresis_state: Dict[str, HysteresisState] = {}  # Track hysteresis per fan
        self._schedule = FanScheduleService(db_session_factory)
        self._profiles = FanProfileService(db_session_factory)
        self._registry: TempSourceRegistry = TempSourceRegistry()
        self._last_pwm_by_fan: Dict[str, int] = {}
        self._last_tick_ts: float = 0.0
        # Rueckgabewerte pro Luefter, beim Start aus der DB geladen. stop()
        # braucht sie ohne Datenbankzugriff (#534).
        self._restore_values: Dict[str, int] = {}
        # Serialisiert start/stop/switch_backend: alle drei tauschen
        # _monitoring_task aus, und eine ueberschriebene Referenz waere eine
        # Regelschleife, die niemand mehr abbrechen kann (#559).
        self._lifecycle_lock = asyncio.Lock()
        # Serialisiert apply_acoustics gegen sich selbst. Loest den
        # Vier-Worker-Fall NICHT -- dafuer sorgt das bedingte Schreiben der
        # Baseline im Store --, wohl aber den haeufigeren Fall zweier
        # gleichzeitiger Anfragen auf demselben Worker (#516).
        self._acoustics_lock = asyncio.Lock()
        # Zuletzt veroeffentlichter Rechtezustand. None heisst: noch nie
        # geschrieben -- dann wird beim ersten Abgleich veroeffentlicht (#552).
        self._published_write_permission: Optional[bool] = None
        # Zuletzt veroeffentlichte Menge gesperrter Kanaele. None heisst wie
        # oben: noch nie geschrieben (#568).
        self._published_denied_fans: Optional[set] = None
        # Die zuletzt im Regelkreis gesehene Freigabe-Menge. Nur dazu da,
        # eine Wiederuebernahme zu ERKENNEN -- sie geschieht ueber einen
        # anderen Worker (#534).
        self._zuletzt_freigegeben: set = set()

        FanControlService._instance = self

    @property
    def schedule(self) -> FanScheduleService:
        """Access the fan schedule service."""
        return self._schedule

    @property
    def profiles(self) -> FanProfileService:
        """Access the fan profile service."""
        return self._profiles

    @classmethod
    async def get_instance(cls, config: Optional[Settings] = None, db_session_factory=None) -> "FanControlService":
        """Get singleton instance."""
        async with cls._lock:
            if cls._instance is None:
                if config is None or db_session_factory is None:
                    raise RuntimeError("FanControlService not initialized")
                cls._instance = cls(config, db_session_factory)
            return cls._instance

    async def start(self, monitoring: bool = True):
        """Start fan control service.

        Args:
            monitoring: If True, start the monitoring loop (primary worker).
                        If False, only initialize backend + configs (secondary workers).
        """
        async with self._lifecycle_lock:
            if not self.config.fan_control_enabled:
                logger.info("Fan control disabled in config")
                return

            # Initialize backend
            await self._initialize_backend()

            if not self._backend:
                logger.warning("No fan control backend available")
                return

            await self._rebuild_registry()

            # Load fan configs from database
            await self._load_fan_configs()

            # Jeder Neustart gibt jedem Kanal eine neue Chance (#534): der
            # Fehlerzaehler, der zur Freigabe gefuehrt hat, lebte im Prozess
            # und ist jetzt weg. Bliebe die Freigabe stehen, haette ein
            # Betreiber, der die Ursache behebt und neu startet, keinen
            # automatischen Rueckweg -- die Karte zeigte weiter "Board regelt"
            # oder, schlimmer, "niemand regelt". Faellt der Kanal wieder aus,
            # ist er nach acht Fehlschlaegen erneut freigegeben; das kostet
            # eine Logzeile und stellt den ehrlichen Zustand her.
            if getattr(lifespan, "IS_PRIMARY_WORKER", False):
                with self.db_session_factory() as db:
                    if read_released_fans(db):
                        publish_released_fans(db, {})
                        logger.info(
                            "Freigaben an die Board-Automatik zurueckgesetzt -- "
                            "jeder Kanal wird neu versucht")
                self._zuletzt_freigegeben = set()

            # Die GPU-Akustik gehoert zum Start, nicht in den Regelzyklus:
            # sie ist Konfiguration, kein Regelkreis (#516).
            try:
                await self.apply_gpu_acoustics()
            except Exception:
                logger.exception("GPU-Akustik konnte nicht angewendet werden")

            # Eine noch laufende Schleife gehoert zum alten Backend und zu
            # den alten Konfigurationen -- und ihre Referenz ginge bei der
            # Zuweisung unten verloren (#559).
            await self._cancel_monitoring_task()

            # Der Rechte-Probe ist beim Backend-Init gelaufen -- sein
            # Ergebnis gehoert zu den Followern, bevor der erste Regelzyklus
            # ueberhaupt stattfindet (#552).
            self.publish_write_permission_if_changed()

            if monitoring:
                # Start monitoring loop (primary worker only)
                self._start_monitoring_task()
            logger.info("Fan control service started (monitoring=%s)", monitoring)

    def publish_write_permission_if_changed(self) -> None:
        """Veroeffentlicht den Rechtezustand des Primary, wenn er sich aendert.

        Nur der Primary schreibt: er ist der einzige Worker, der die Hardware
        im Regelbetrieb ueberhaupt anfasst und dessen Stand sich damit heilen
        kann. Ein Follower wuerde seinen ungeheilten Startwert ueber den
        gemessenen des Primary schreiben.

        Der Aufruf sitzt im 5-Sekunden-Takt der Regelschleife -- geschrieben
        wird deshalb nur bei echter Aenderung. Ein Schreibvorgang je Tick
        waere dieselbe Sorte Last, die #533 beseitigt hat.
        """
        if not getattr(lifespan, "IS_PRIMARY_WORKER", False):
            return
        # has_write_permission() statt des rohen Attributs (#568): das
        # Attribut kann nur True werden, die Methode leitet den Stand aus
        # den Kanalzustaenden ab und kann damit auch zurueckfallen.
        holen = getattr(self._backend, "has_write_permission", None)
        current = holen() if callable(holen) else getattr(
            self._backend, "_has_write_permission", None)
        if current is None:
            return

        # Die betroffenen Kanaele mitveroeffentlichen (#568 Punkt 2): sie
        # leben im _fan_cache dessen, der schreibt -- also nur hier. Ohne das
        # meldeten die drei Follower fuer denselben Kanal weiter `supported`
        # und das Badge flackerte im 5-Sekunden-Poll.
        denied = self._denied_fan_ids()
        if (current == self._published_write_permission
                and denied == self._published_denied_fans):
            return
        with self.db_session_factory() as db:
            if publish_write_permission(db, current, denied):
                self._published_write_permission = current
                self._published_denied_fans = denied

    def _denied_fan_ids(self) -> Optional[set]:
        """Die Kanaele, auf denen der Backend-Cache ein EACCES vermerkt hat.

        None heisst "unbekannt" -- etwa beim Dev-Backend, das gar keinen
        solchen Cache fuehrt. Eine leere Menge waere hier die Behauptung "kein
        Kanal ist gesperrt", und die wuerde veroeffentlicht; None laesst die
        gespeicherte Liste unberuehrt.
        """
        cache = getattr(self._backend, "_fan_cache", None)
        if not isinstance(cache, dict):
            return None
        return {
            fan_id for fan_id, info in cache.items()
            if isinstance(info, dict)
            and info.get("pwm_control") is PwmControl.NO_PERMISSION
        }

    async def _cancel_monitoring_task(self) -> None:
        """Bricht eine laufende Regelschleife ab und gibt die Referenz frei.

        Immer vor einer Neuzuweisung aufzurufen: eine ueberschriebene
        Referenz laesst die alte Task unerreichbar weiterlaufen.
        """
        task = self._monitoring_task
        self._monitoring_task = None
        self._is_running = False
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    def _start_monitoring_task(self) -> None:
        self._is_running = True
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())

    async def stop(self):
        """Stop fan control service."""
        async with self._lifecycle_lock:
            # Erst die Schleife stilllegen, dann zurueckgeben -- umgekehrt
            # schriebe sie im naechsten Zyklus pwm_enable=1 gegen die
            # Rueckgabe (#534).
            await self._cancel_monitoring_task()

            try:
                await self._release_all_to_board()
            except Exception:
                logger.exception("Rueckgabe an die Board-Automatik fehlgeschlagen")

            logger.info("Fan control service stopped")

    async def _release_all_to_board(self) -> None:
        """Gibt alle Luefter mit bekanntem Rueckgabewert an die Automatik zurueck.

        Entschieden wird am Ist-Wert in sysfs statt an einer Besitz-Buchfuehrung.
        Ein Luefter im MANUAL-Modus wird vom Regelkreis nie geschrieben (Ziel ==
        Ist), sein einziger Schreibweg ist die HTTP-Route -- und die landet bei
        vier Workern meist auf einem Sekundaer. Eine primary-gebundene
        Besitzverfolgung haette ihn nie erfasst, und genau er stuende am Ende
        ungeregelt da.
        """
        if not getattr(lifespan, "IS_PRIMARY_WORKER", False):
            return
        if not self._restore_values:
            return

        cache = getattr(self._backend, "_fan_cache", None) or {}
        released = 0
        failed = 0

        for fan_id, target in self._restore_values.items():
            info = cache.get(fan_id)
            if not isinstance(info, dict):
                continue
            if info.get("gpu_vendor") is not None:
                continue
            pwm_enable_path = info.get("pwm_enable_path")
            if pwm_enable_path is None:
                continue

            current = await self._backend._read_hwmon_file(pwm_enable_path)
            if not needs_release(current, target):
                continue

            if await self._backend.release_to_board(fan_id, target):
                released += 1
            else:
                failed += 1

        if released or failed:
            logger.info(
                "Rueckgabe an die Board-Automatik: %d erfolgreich, %d fehlgeschlagen",
                released, failed,
            )

    async def apply_gpu_acoustics(self) -> Dict[str, bool]:
        """Startpfad: nur der Primary wendet an.

        Beim Start wuerden sonst vier Uvicorn-Worker dieselben vier Werte
        gegeneinander setzen (#555, #559).

        Das Gate sitzt bewusst NUR hier und nicht in apply_acoustics: eine
        ausdrueckliche Nutzeraktion ueber den PUT-Endpunkt landet auf dem
        Worker, der die Anfrage bedient -- bei vier Workern in drei von vier
        Faellen auf einem Follower. Steckte das Gate weiter innen, quittierte
        der Endpunkt mit 200 und aenderte an der Karte nichts.
        """
        if not getattr(lifespan, "IS_PRIMARY_WORKER", False):
            return {}
        return await self.apply_acoustics()

    async def apply_acoustics(
        self,
        desired: Optional[Mapping[str, Optional[int]]] = None,
    ) -> Dict[str, bool]:
        """Beobachtet die Baseline und wendet die gewuenschten Werte an (#516).

        Ohne Primary-Gate -- siehe apply_gpu_acoustics.

        Args:
            desired: Die anzuwendenden Wuensche. None heisst: das
                gespeicherte desired nehmen (Startpfad). Der PUT reicht seine
                Wuensche hier herein, BEVOR er sie persistiert -- gespeichert
                wird nur, was die Karte angenommen hat.

        Returns:
            Je angefasstem Knoten, ob der Wert danach tatsaechlich anliegt.
            Der Rueckgabewert wurde frueher verschluckt, und mit ihm die
            Ruecklese-Kontrolle, die auf dieser Karte der einzige Beleg fuer
            einen wirksamen Write ist (#480).
        """
        fan_ctrl = self._gpu_fan_ctrl_dir()
        if fan_ctrl is None:
            return {}

        async with self._acoustics_lock:
            if desired is None:
                # Fail-soft: ein Lesefehler darf den Start nicht verhindern.
                # Geschrieben wird auf diesem Pfad nichts, was die Baseline
                # beschaedigen koennte -- capture_baseline liest selbst frisch.
                with self.db_session_factory() as db:
                    desired = load_acoustics_config_fail_soft(db).desired.model_dump()

            wanted = {name: value for name, value in desired.items()
                      if value is not None}
            if not wanted:
                return {}

            current = await read_acoustics(fan_ctrl)

            # Baseline VOR dem ersten Write erfassen -- und nur, wo noch
            # nichts steht. Das Nur-wenn-leer entscheidet der Store anhand
            # der frisch gelesenen Zeile, nicht anhand eines Snapshots, der
            # beim Lesen der Hardware schon ueberholt sein kann.
            observed = {name: node.value for name, node in current.items()
                        if name in wanted}
            if observed:
                try:
                    with self.db_session_factory() as db:
                        capture_baseline(db, observed)
                except AcousticsConfigError as exc:
                    logger.warning(
                        "Baseline nicht erfassbar, kein Akustik-Write: %s", exc)
                    return {}

            results: Dict[str, bool] = {}
            for name, value in wanted.items():
                results[name] = await write_acoustic(
                    fan_ctrl, name, value, self._backend._write_hwmon_file
                )
            return results

    def _gpu_fan_ctrl_dir(self) -> Optional[Path]:
        """Das fan_ctrl-Verzeichnis der AMD-GPU, falls die Karte es anbietet.

        Gefunden wird es ueber einen gescannten GPU-Luefter, obwohl die
        Akustikwerte der KARTE gehoeren. Hat die Karte keinen gescannten
        Luefter -- etwa weil fan1_input fehlt --, bleibt das Panel aus,
        obwohl die Schnittstelle vorhanden waere. Auf der Referenzhardware
        tritt das nicht auf; eine zweite Geraeteaufloesung dafuer zu bauen
        waere Aufwand ohne belegten Anlass (#516).
        """
        cache = getattr(self._backend, "_fan_cache", None)
        if not isinstance(cache, dict):
            return None
        for info in cache.values():
            if not isinstance(info, dict) or info.get("gpu_vendor") != "amd":
                continue
            pwm_path = info.get("pwm_path")
            if pwm_path is None:
                continue
            found = find_fan_ctrl_dir(pwm_path.parent)
            if found is not None:
                return found
        return None

    async def _initialize_backend(self):
        """Initialize appropriate backend."""
        # Check if forcing dev backend
        if self.config.fan_force_dev_backend or self.config.is_dev_mode:
            logger.info("Using dev fan control backend (simulated)")
            self._backend = DevFanControlBackend(self.config)
            self._use_linux_backend = False
            return

        # Try Linux backend
        linux_backend = LinuxFanControlBackend(self.config)
        if await linux_backend.is_available():
            logger.info("Using Linux fan control backend (hardware)")
            self._backend = linux_backend
            self._use_linux_backend = True
        else:
            logger.info("Linux backend unavailable, using dev backend")
            self._backend = DevFanControlBackend(self.config)
            self._use_linux_backend = False

    def _should_reconcile(self, chip_count: int) -> bool:
        """Beide Vorbedingungen sind hart -- ihr Fehlen bedeutet Totalverlust.

        Ohne Linux-Backend liefe der Abgleich gegen eine Chip-Menge ohne
        einen einzigen hwmon-Chip; ohne gefundenen Chip gegen eine leere.
        In beiden Faellen faende keine Altzeile ihren Chip wieder.
        """
        if not getattr(lifespan, "IS_PRIMARY_WORKER", False):
            return False
        if not self._use_linux_backend:
            return False
        return chip_count > 0

    def _collect_chip_facts(self) -> Dict[str, ChipFacts]:
        """Chipname -> Kennung, vorhandene PWM-Kanaele, Mehrdeutigkeit."""
        by_prefix: Dict[str, Dict] = {}
        fan_cache = getattr(self._backend, "_fan_cache", None)
        if not isinstance(fan_cache, dict):
            # Schuetzt NICHT vor einer realen Produktionslage -- das echte
            # LinuxFanControlBackend liefert hier immer ein dict. Der Fall
            # tritt nur auf, wenn self._backend kein solches Attribut kennt
            # (DevFanControlBackend) oder ein Test-Double (z. B. ein
            # unspezifizierter AsyncMock()) ein Attribut liefert, das selbst
            # wieder ein Mock statt eines dict ist. Beides wird wie ein
            # leerer Scan behandelt: kein Chip, kein Abgleich.
            fan_cache = {}
        for fan_id, info in fan_cache.items():
            if not info.get("identity_stable"):
                continue
            prefix = info.get("device_driver") or "Unknown"
            key, _, channel = fan_id.rpartition(":pwm")
            if not channel.isdigit():
                continue
            entry = by_prefix.setdefault(prefix, {"keys": set(), "channels": set()})
            entry["keys"].add(key)
            entry["channels"].add(int(channel))

        facts: Dict[str, ChipFacts] = {}
        for prefix, entry in by_prefix.items():
            keys = entry["keys"]
            facts[prefix] = ChipFacts(
                key=next(iter(sorted(keys))),
                pwm_channels=frozenset(entry["channels"]),
                ambiguous=len(keys) > 1,
            )
        return facts

    def _collect_sensor_map(self) -> Dict[str, str]:
        """Alt-Sensor-ID (hwmon<N>_temp<M>) -> neue, praefixierte Kennung."""
        mapping: Dict[str, str] = {}
        paths = getattr(self._backend, "_temp_paths", None)
        if not isinstance(paths, dict):
            # Gleiche Absicherung wie in _collect_chip_facts oben: schuetzt
            # vor Backend-Attributen, die kein dict sind (unspezifizierter
            # Test-Mock, ein kuenftiges Backend ohne dieses Attribut) --
            # nicht vor einer realen Produktionslage.
            paths = {}
        for stable_id, path in paths.items():
            hwmon_name = path.parent.name
            temp_num = path.name[len("temp"):-len("_input")]
            mapping[f"{hwmon_name}_temp{temp_num}"] = f"hwmon:{stable_id}"
        return mapping

    def _collect_pwm_enable_observations(self) -> Dict[str, int]:
        """Beobachtete Automatikmodi aus dem Scan-Cache.

        GPU-Luefter bleiben draussen: fuer AMD-Karten existiert mit
        AmdManualState / disable_amd_manual bereits ein eigener Rueckgabeweg,
        der zusaetzlich das Performance-Level zuruecksetzt, und nouveau hat
        gar keinen. Der isinstance-Schutz folgt dem Muster, das fuer dieselben
        Cache-Zugriffe in #532 eingefuehrt wurde.
        """
        cache = getattr(self._backend, "_fan_cache", None)
        if not isinstance(cache, dict):
            # Gleiche Absicherung wie in _collect_chip_facts/_collect_sensor_map:
            # ein unspezifizierter Test-Mock (z. B. AsyncMock()) liefert hier
            # selbst wieder einen Mock statt eines dict -- ohne diese Pruefung
            # wuerde cache.items() als Coroutine zurueckkommen (AsyncMock-
            # Kindattribute sind selbst AsyncMock) und die Iteration bricht.
            cache = {}
        return {
            fan_id: info["pwm_enable_at_scan"]
            for fan_id, info in cache.items()
            if isinstance(info, dict)
            and info.get("gpu_vendor") is None
            and is_observation(info.get("pwm_enable_at_scan"))
        }

    def _persist_restore_values(self, observations: Dict[str, int]) -> None:
        """Beobachtete pwm_enable-Werte speichern und in den Speicher laden.

        Nur der Primary schreibt. Geschrieben wird ausschliesslich bei echter
        Aenderung, und updated_at wird dabei ausdruecklich mitgefuehrt: die
        Spalte traegt onupdate=func.now() und ist das Rangkriterium des
        Identitaets-Abgleichs (fan_reconcile.py). Ein Schreibvorgang bei jedem
        Start setzte jede Zeile auf "gerade angefasst".
        """
        if not getattr(lifespan, "IS_PRIMARY_WORKER", False):
            return

        with self.db_session_factory() as db:
            rows = list(db.execute(select(FanConfig)).scalars())
            by_id = {row.fan_id: row for row in rows}

            changed = 0
            for fan_id, row in by_id.items():
                target = resolve_restore_value(observations.get(fan_id),
                                               row.pwm_enable_restore)
                if target is not None:
                    self._restore_values[fan_id] = target
                if target == row.pwm_enable_restore or target is None:
                    continue
                db.execute(
                    update(FanConfig)
                    .where(FanConfig.id == row.id)
                    .values(pwm_enable_restore=target,
                            updated_at=row.updated_at)
                )
                changed += 1
                logger.info(
                    "Rueckgabewert fuer %s beobachtet: pwm_enable=%s",
                    fan_id, target,
                )
            if changed:
                db.commit()

    async def _load_fan_configs(self):
        """Load fan configurations from database.

        For new fans (first discovery), assigns the best available CPU sensor
        as the default temp_sensor_id. Existing configs are NOT modified —
        user-chosen sensors (including composite sensors) survive service restarts.
        """
        if not self._backend:
            return

        fans = await self._backend.get_fans()

        # Determine best CPU sensor for new fan defaults only
        cpu_sensor_id: Optional[str] = None
        try:
            sensors = await self._backend.get_available_temp_sensors()
            for s in sensors:
                if s.is_cpu_sensor:
                    cpu_sensor_id = s.sensor_id
                    break
        except Exception:
            pass

        observations = self._collect_pwm_enable_observations()

        with self.db_session_factory() as db:
            chip_facts = self._collect_chip_facts()
            if self._should_reconcile(len(chip_facts)):
                try:
                    report = reconcile_fan_identities(
                        db,
                        chips=chip_facts,
                        sensor_map=self._collect_sensor_map(),
                        cpu_sensor_id=TempSourceRegistry._normalize_id(cpu_sensor_id)
                        if cpu_sensor_id else None,
                    )
                    # Eigenstaendiger Commit VOR dem Audit-Eintrag: der
                    # Abgleich muss die Datenbank erreicht haben, BEVOR die
                    # Anlage-Schleife unten startet (R4) -- und bevor der
                    # Audit-Aufruf unten laeuft, damit dessen eigene Session
                    # (db=None, siehe unten) nicht ueber unsere entscheidet,
                    # ob unser Commit stattfand. db.commit() steht bewusst
                    # noch IM try: die eigentlichen ORM-Schreibzugriffe des
                    # Abgleichs (Umbenennung, Deaktivierung) erreichen die
                    # Datenbank erst beim Flush, das der Commit ausloest --
                    # ein UNIQUE-Verstoss aus einem Rename wuerde sonst erst
                    # hier auftreten und aus dem try entkommen.
                    db.commit()
                    if report.renamed or report.deactivated or report.unresolved_sensors:
                        try:
                            # Eigene Session (db=None): AuditLoggerDB.log_event
                            # committet die uebergebene Session selbst. Mit
                            # unserer db haette ein fehlschlagender Audit-Commit
                            # unsere bereits erfolgreiche Transaktion getroffen
                            # und den echten Fehler als Audit-Problem maskiert.
                            from app.services.audit import get_audit_logger_db
                            get_audit_logger_db().log_system_event(
                                action="fan_identity_reconcile",
                                details={
                                    "renamed": report.renamed,
                                    "deactivated": report.deactivated,
                                    "skipped_absent": report.skipped_absent,
                                    # M-3: eine nicht aufloesbare Sensor-Zuordnung
                                    # tauscht die Nutzerwahl stillschweigend gegen
                                    # den CPU-Default aus -- die einzige
                                    # Nutzeraenderung dieses Laufs, die sonst
                                    # nirgends revisionssicher gelandet waere.
                                    "unresolved_sensors": report.unresolved_sensors,
                                },
                                db=None,
                            )
                        except Exception:
                            logger.debug("Audit-Eintrag zum Identitaets-Abgleich fehlgeschlagen")
                    # M-6: _rebuild_registry() lief in start() VOR diesem Abgleich
                    # und hat Labels/Composite-Quellen deshalb aus der noch
                    # NICHT migrierten Datenbank gelesen. Ohne diesen zweiten
                    # Aufruf gaelten im ersten Start nach dem Upgrade die alten
                    # Schluessel bis zum naechsten Neustart. Eigenes try: der
                    # Abgleich selbst ist zu diesem Zeitpunkt bereits committet
                    # und erfolgreich -- ein Fehler beim Neuaufbau der Registry
                    # darf nicht als Abgleichs-Fehlschlag geloggt werden und
                    # nicht die Anlage-Schleife unten blockieren.
                    try:
                        await self._rebuild_registry()
                    except Exception:
                        logger.debug("Registry-Neuaufbau nach Abgleich fehlgeschlagen")
                except Exception:
                    # Nicht weitermachen: die Scan-IDs liegen bereits in der
                    # neuen Form vor, die DB-Zeilen aber noch in der alten.
                    # Liefe die Anlage-Schleife trotzdem, legte sie frische
                    # Default-Configs unter den neuen IDs an -- deren
                    # updated_at ist "jetzt" und gewaenne beim naechsten
                    # Abgleich gegen die echte Nutzerkurve. Das waere genau
                    # der Datenverlust, den dieser Abgleich verhindern soll,
                    # nur auf einem Umweg. Stattdessen: kein neuer
                    # Fan-Datensatz -- die Luefter bleiben fuer diesen einen
                    # Startzyklus ungeregelt (sichtbar: PWM bewegt sich nicht,
                    # keine Kurve in der UI), aber keine Zeile geht verloren.
                    # Der naechste Start versucht es erneut.
                    logger.exception(
                        "Identitaets-Abgleich fehlgeschlagen -- keine Configs "
                        "angelegt, um die Altzeilen nicht zu ueberdecken. Die "
                        "Luefter bleiben bis zum naechsten Start ungeregelt."
                    )
                    return

            if not getattr(lifespan, "IS_PRIMARY_WORKER", False):
                # Die Anlage-Schleife ist ebenso primary-only wie der Abgleich
                # oben (C1): der Sekundaer-Worker durchlaeuft beim Start KEINE
                # start_power_manager(primary=True)/check_and_notify_permissions()
                # zwischen Primary-Flag und Fan-Start (siehe lifespan.py) und
                # erreicht diese Stelle deshalb plausibel VOR dem Primary.
                # Legte er hier eine Default-Config unter einer (noch) neuen
                # Scan-ID an, traegt sie updated_at="jetzt" und gewinnt beim
                # spaeteren Abgleich des Primary gegen die echte Nutzerkurve
                # -- genau die Zeile, die der Abgleich schuetzen soll, ginge
                # ueber den Sekundaer-Worker doch noch verloren. Sekundaer-
                # Worker lesen daher nur; die Configs liegen in der
                # gemeinsamen Datenbank, der Primary legt sie an. Ein
                # Sekundaer, der kurz davor eine Anfrage bedient, zeigt einen
                # Luefter ohne Config -- transient und harmlos.
                logger.debug("Sekundaer-Worker: Anlage-Schleife uebersprungen")
                return

            # Simulierte Luefter gehoeren nur in eine Dev-Datenbank. Ein
            # Produktionsdienst, der ueber POST /api/fans/backend auf das
            # Dev-Backend geschaltet wurde, sieht sonst Zeilen an, die
            # niemand wieder los wird: der Identitaets-Abgleich fasst sie
            # mangels stabiler Chip-Kennung nicht an, und ein
            # Zurueckschalten entfernt sie nicht (#558).
            creatable = fans if (self._use_linux_backend
                                 or self.config.is_dev_mode) else []
            if fans and not creatable:
                logger.info(
                    "Dev-Backend ausserhalb des Dev-Modus: keine Konfiguration "
                    "fuer %d simulierte Luefter angelegt", len(fans),
                )

            for fan in creatable:
                existing = db.execute(
                    select(FanConfig).where(FanConfig.fan_id == fan.fan_id)
                ).scalar_one_or_none()

                if not existing:
                    # Create new config with CPU sensor if available
                    config = FanConfig(
                        fan_id=fan.fan_id,
                        name=fan.name,
                        mode=FanMode.AUTO.value,
                        curve_json=json.dumps([p.model_dump() for p in fan.curve_points]),
                        min_pwm_percent=fan.min_pwm_percent,
                        max_pwm_percent=fan.max_pwm_percent,
                        emergency_temp_celsius=fan.emergency_temp_celsius,
                        temp_sensor_id=TempSourceRegistry._normalize_id(
                            cpu_sensor_id or fan.temp_sensor_id
                        ) if (cpu_sensor_id or fan.temp_sensor_id) else None,
                        is_active=True,
                        pwm_enable_restore=observations.get(fan.fan_id),
                    )
                    try:
                        # Savepoint statt db.rollback() auf der ganzen
                        # Transaktion: sonst risse eine kollidierende fuenfte
                        # Zeile die vier zuvor erfolgreich geflushten wieder
                        # mit sich (I3). Ein anderer Worker war schneller --
                        # die Zeile existiert, das ist der gewuenschte
                        # Endzustand.
                        #
                        # M-4: seit dem Primary-only-Gate direkt oberhalb (der
                        # fruehe return bei nicht-Primary) ist dieser Zweig in
                        # der Praxis kaum noch erreichbar -- ein weiterer
                        # Uvicorn-Worker mit demselben Primary-Anspruch waere
                        # der einzige verbleibende Weg zu einem Wettlauf um
                        # dieselbe Zeile. Bewusst NICHT entfernen: der
                        # Savepoint ist billig und die einzige Absicherung
                        # gegen genau diesen (seltenen) Fall. Nicht als toten
                        # Code streichen.
                        with db.begin_nested():
                            db.add(config)
                    except IntegrityError:
                        logger.debug("Fan-Config %s wurde parallel angelegt", fan.fan_id)

            db.commit()

        self._persist_restore_values(observations)

        logger.info(f"Loaded {len(fans)} fan configuration(s)")

    async def _rebuild_registry(self) -> None:
        """(Re)populate the registry with all current sources."""
        self._registry.clear()
        if not self._backend:
            return

        # hwmon sensors (from backend). amdgpu/nouveau entries are skipped —
        # the same physical sensors are exposed via the gpu:* namespace below,
        # which is the canonical source. Listing both would show every GPU
        # temperature twice in the SensorsPanel.
        _GPU_DRIVERS = {"amdgpu", "nouveau"}
        try:
            hwmon_sensors = await self._backend.get_available_temp_sensors()
            for s in hwmon_sensors:
                if s.device_name in _GPU_DRIVERS:
                    continue
                sid = s.sensor_id
                src = HwmonTempSource(
                    sensor_id=sid,
                    device_name=s.device_name,
                    backend_label=s.label,
                    is_cpu_sensor=s.is_cpu_sensor,
                    read_fn=self._make_hwmon_reader(sid),
                )
                self._registry.register(src)
        except Exception as exc:
            logger.debug("hwmon source registration failed: %s", exc)

        # GPU sources from monitoring SHM
        for channel in ("edge", "junction", "mem"):
            self._registry.register(GpuTempSource(
                channel=channel,
                read_fn=self._make_gpu_reader(channel),
            ))

        # Disk sources from SMART cache
        for device in await self._list_smart_devices():
            self._registry.register(DiskTempSource(
                device=device,
                read_fn=self._make_disk_reader(device),
            ))

        # Composite sensors from DB
        await self._register_composites_from_db()

        # Custom labels from DB
        await self._load_sensor_labels()

    def _make_hwmon_reader(self, sensor_id: str):
        async def _read():
            try:
                return await self._backend.get_temperature(sensor_id)
            except Exception:
                return None
        return _read

    def _make_gpu_reader(self, channel: str):
        async def _read():
            from app.services.monitoring.shm import read_shm, TELEMETRY_FILE
            data = read_shm(TELEMETRY_FILE, max_age_seconds=30.0)
            if not data:
                return None
            gpu = data.get("gpu") if isinstance(data, dict) else None
            if not gpu:
                return None
            key = {
                "edge": "temperature_edge_celsius",
                "junction": "temperature_junction_celsius",
                "mem": "temperature_memory_celsius",
            }[channel]
            v = gpu.get(key)
            return float(v) if v is not None else None
        return _read

    def _read_smart_summary(self) -> Dict[str, float]:
        """Read disk SMART summary from SHM, return {device_name: temp_celsius}.

        Empty dict when SHM file missing, stale, or malformed. The monitoring
        worker publishes this file every 60s via _write_smart_summary_snapshot.
        """
        try:
            from app.services.monitoring.shm import read_shm, SMART_SUMMARY_FILE
            payload = read_shm(SMART_SUMMARY_FILE, max_age_seconds=180.0)
            if not payload:
                return {}
            out: Dict[str, float] = {}
            for d in payload.get("devices", []) or []:
                name = d.get("name")
                temp = d.get("temperature_celsius")
                if name and temp is not None:
                    out[name] = float(temp)
            return out
        except Exception:
            return {}

    def _make_disk_reader(self, device: str):
        async def _read():
            return self._read_smart_summary().get(device)
        return _read

    async def _list_smart_devices(self) -> List[str]:
        return list(self._read_smart_summary().keys())

    async def _refresh_disk_sources(self) -> None:
        """Reconcile disk:* registry entries with the current SMART summary.

        Adds new disks that appeared and removes ones that vanished, without
        touching hwmon/gpu/mix sources. Called from the sensor-list endpoint
        so the UI reflects fresh data without a full registry rebuild.
        """
        desired = set(self._read_smart_summary().keys())
        current = {
            s.id for s in self._registry.all_sources() if s.kind == "disk"
        }

        for device in desired:
            sid = f"disk:{device}"
            if sid not in current:
                self._registry.register(DiskTempSource(
                    device=device,
                    read_fn=self._make_disk_reader(device),
                ))

        for sid in current - {f"disk:{d}" for d in desired}:
            self._registry.unregister(sid)

    async def _register_composites_from_db(self) -> None:
        from app.models.fans import CompositeTempSensor
        with self.db_session_factory() as db:
            rows = db.execute(select(CompositeTempSensor)).scalars().all()
            for row in rows:
                try:
                    source_ids = json.loads(row.source_ids_json)
                except Exception:
                    continue
                self._registry.register(MixTempSource(
                    composite_id=row.id,
                    name=row.name,
                    function=row.function,
                    source_ids=source_ids,
                    registry=self._registry,
                ))

    async def _load_sensor_labels(self) -> None:
        from app.models.fans import TempSensorLabel
        with self.db_session_factory() as db:
            for row in db.execute(select(TempSensorLabel)).scalars().all():
                self._registry.set_label(row.sensor_id, row.custom_label)

    async def _monitoring_loop(self):
        """Background monitoring loop."""
        logger.info("Fan control monitoring loop started")
        sample_count = 0

        while self._is_running:
            try:
                await self._monitor_and_control_fans()
                # Sagt die Ableitung gerade `readonly`, noch einmal probieren
                # (#568): der Regelkreis schreibt einen Luefter im
                # MANUAL-Modus nie, und die Anzeige sperrt die
                # Bedienelemente -- ohne diese Probe gaebe es keinen Weg
                # zurueck ausser einem Dienst-Neustart. Die Methode taktet
                # sich selbst und ist ein No-op, solange geschrieben werden
                # darf.
                erneut = getattr(self._backend, "recheck_write_permission", None)
                if erneut is not None:
                    await erneut()
                # Nach dem Regelzyklus: ein erfolgreicher Write kann den
                # Rechtezustand geheilt haben, den die Follower nur ueber
                # die veroeffentlichte Zeile erfahren (#552).
                self.publish_write_permission_if_changed()

                sample_count += 1

                # Persist to DB every 12 samples (1 minute at 5s interval)
                if sample_count % 12 == 0:
                    await self._persist_samples()

                await asyncio.sleep(self.config.fan_sample_interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in fan monitoring loop: {e}", exc_info=True)
                await asyncio.sleep(self.config.fan_sample_interval_seconds)

    async def _monitor_and_control_fans(self):
        """Monitor and control fans based on configuration."""
        if not self._backend:
            return

        fans = await self._backend.get_fans()
        now_ts = _time.time()
        dt = (now_ts - self._last_tick_ts) if self._last_tick_ts else self.config.fan_sample_interval_seconds
        self._last_tick_ts = now_ts

        # Map for sync curve type
        other_fan_pwms = {f.fan_id: f.pwm_percent for f in fans}

        # Der Besitzzustand je Kanal (#534). Einmal je Zyklus gelesen statt je
        # Luefter: es ist dieselbe Singleton-Zeile.
        with self.db_session_factory() as db:
            freigegeben = read_released_fans(db)
        freigaben_vorher = dict(freigegeben)

        # Eine Wiederuebernahme kommt ueber einen BELIEBIGEN Worker (die Route
        # laeuft dort, wo die Anfrage landet), der Fehlerzaehler lebt aber im
        # Prozess des Primary. Ohne diesen Abgleich saehe er den Kanal zwar
        # wieder als besessen, fragte aber seinen eigenen -- weiterhin am
        # Deckel stehenden -- Zaehler und gaebe ihn im selben Zyklus erneut ab.
        # Der Nutzer bekaeme einen Erfolg gemeldet und fuenf Sekunden spaeter
        # wieder "Board regelt" (#534).
        zurueckgeholt = self._zuletzt_freigegeben - set(freigegeben)
        for fan_id in zurueckgeholt:
            self._backend.clear_write_failures(fan_id)
            self._hysteresis_state.pop(fan_id, None)
            aktuell = next((f for f in fans if f.fan_id == fan_id), None)
            if aktuell is not None:
                # Genau EIN erzwungener Write, sonst bliebe pwm_enable auf dem
                # Auto-Wert stehen, falls das Board zufaellig denselben PWM
                # eingestellt hat, den die Kurve berechnet -- der Regelkreis
                # schreibt nur bei Wertaenderung.
                await self._backend.set_pwm(fan_id, aktuell.pwm_percent, force=True)
            logger.info("%s: wieder uebernommen, Fehlerzaehler zurueckgesetzt", fan_id)
        self._zuletzt_freigegeben = set(freigegeben)

        with self.db_session_factory() as db:
            for fan in fans:
                config = db.execute(
                    select(FanConfig).where(FanConfig.fan_id == fan.fan_id)
                ).scalar_one_or_none()
                if not config or not config.is_active:
                    continue

                mode = FanMode(config.mode)
                temperature = await self._registry.get_temp(config.temp_sensor_id) if config.temp_sensor_id else None

                target_pwm = fan.pwm_percent

                if mode in (FanMode.AUTO, FanMode.SCHEDULED):
                    if temperature is not None and temperature >= config.emergency_temp_celsius:
                        target_pwm = 100
                        mode = FanMode.EMERGENCY
                        if fan.fan_id in self._hysteresis_state:
                            del self._hysteresis_state[fan.fan_id]
                        try:
                            from app.services.notifications.events import emit_temperature_critical_sync
                            emit_temperature_critical_sync(config.temp_sensor_id or fan.fan_id, temperature)
                        except Exception:
                            pass
                    else:
                        if temperature is not None and temperature >= config.emergency_temp_celsius - 10:
                            try:
                                from app.services.notifications.events import emit_temperature_high_sync
                                emit_temperature_high_sync(config.temp_sensor_id or fan.fan_id, temperature)
                            except Exception:
                                pass

                        # Schedule override of curve_json (graph mode only)
                        curve_json = config.curve_json
                        if FanMode(config.mode) == FanMode.SCHEDULED:
                            scheduled_pts, _ = self._schedule.resolve_active_curve(
                                fan.fan_id, config.curve_json, db
                            )
                            curve_json = json.dumps([p if isinstance(p, dict) else p.model_dump() for p in scheduled_pts]) if scheduled_pts else config.curve_json

                        eval_cfg = type("CfgView", (), {
                            **{c.name: getattr(config, c.name) for c in config.__table__.columns},
                            "curve_json": curve_json,
                        })()

                        prev = self._last_pwm_by_fan.get(fan.fan_id, fan.pwm_percent)

                        def _profile_loader(pid: Optional[int]) -> List[dict]:
                            if pid is None:
                                return []
                            from app.models.fans import FanCurveProfile
                            row = db.execute(select(FanCurveProfile).where(FanCurveProfile.id == pid)).scalar_one_or_none()
                            if row is None or not row.curve_json:
                                return []
                            try:
                                return json.loads(row.curve_json)
                            except Exception:
                                return []

                        target_pwm = evaluate_curve(
                            eval_cfg, temperature, prev, other_fan_pwms, _profile_loader, dt,
                        )
                        if eval_cfg.curve_type == "graph" and temperature is None:
                            # #517-Folgeschaden: _interpolate() liefert 0 fuer
                            # temp=None (kein temp_sensor_id, oder der Sensor
                            # liefert nicht). Ein ausgefallener Sensor darf die
                            # Kuehlung nicht abstellen -> aktuellen PWM halten.
                            target_pwm = fan.pwm_percent
                        # Hysteresis dampens the already-computed target (only for graph-like outputs)
                        target_pwm = self._apply_hysteresis(
                            fan.fan_id, temperature or 0.0,
                            getattr(config, "hysteresis_celsius", 3.0), target_pwm,
                        ) if eval_cfg.curve_type == "graph" else target_pwm

                target_pwm = max(config.min_pwm_percent, min(config.max_pwm_percent, target_pwm))

                if fan.pwm_control is PwmControl.FIRMWARE_MANAGED:
                    # Die Firmware besitzt die Kurve (RDNA3+). Kein Write-Versuch,
                    # und der Sample protokolliert den tatsaechlichen Wert.
                    target_pwm = fan.pwm_percent

                # --- Rueckgabe an die Board-Automatik (#534 Punkt 1) ---------
                #
                # Die Stelle ist mit Bedacht gewaehlt: KEIN `continue` weiter
                # oben. Der Uebersprung sitzt hier, weil damit alles darueber
                # weiterlaeuft -- die Temperaturlesung, die Notfall-Emitter und
                # weiter unten der Sample-Puffer. Ein `continue` nach dem
                # Config-Load haette die Messwerte mitgenommen, und der
                # Verlaufsgraph risse genau dort ab, wo man nachsieht.
                #
                # Wirksam wird die Freigabe ueber denselben Weg wie
                # FIRMWARE_MANAGED zwei Zeilen darueber: target_pwm auf den
                # Ist-Wert, damit die Write-Bedingung nicht greift. Das schreibt
                # nebenbei _last_pwm_by_fan auf den echten Wert fort -- sonst
                # ginge nach einer Wiederuebernahme ein minutenalter Wert in die
                # Glaettung ein.
                zustand = FanOwnership(freigegeben.get(fan.fan_id, FanOwnership.OWNED))

                # Die Rueckgabe ist ein Hardware-Write und gehoert dem
                # Primary -- so wie _release_all_to_board() beim Dienst-Ende
                # (#465). Der Regelkreis laeuft ohnehin nur dort; die Pruefung
                # steht trotzdem da, weil die Folge eines Irrtums ein Luefter
                # waere, den zwei Prozesse gegeneinander umschalten.
                ist_primary = getattr(lifespan, "IS_PRIMARY_WORKER", False)
                if zustand is FanOwnership.OWNED and ist_primary:
                    fehlschlaege, am_deckel = self._backend.write_failure_state(
                        fan.fan_id)
                    if should_release(
                        at_write_cap=am_deckel,
                        ownership=zustand,
                        has_observed_restore_value=(
                            self._restore_values.get(fan.fan_id) is not None
                        ),
                        is_firmware_managed=(
                            fan.pwm_control is PwmControl.FIRMWARE_MANAGED
                        ),
                        is_active=bool(config.is_active),
                    ):
                        geglueckt = await self._backend.release_to_board(
                            fan.fan_id, self._restore_values[fan.fan_id]
                        )
                        zustand = ownership_after_release(geglueckt)
                        freigegeben[fan.fan_id] = zustand.value
                        # Die Hysterese eingefroren stehen zu lassen, hiesse
                        # nach der Wiederuebernahme gegen einen alten
                        # Referenzwert zu daempfen.
                        self._hysteresis_state.pop(fan.fan_id, None)
                        logger.warning(
                            "%s: nicht steuerbar (%d Fehlschlaege in Folge) -- "
                            "%s", fan.fan_id, fehlschlaege,
                            "an die Board-Automatik zurueckgegeben"
                            if geglueckt else
                            "Rueckgabe gescheitert, es regelt niemand",
                        )

                if is_released(zustand):
                    target_pwm = fan.pwm_percent

                if target_pwm != fan.pwm_percent:
                    # Im Notfall das Backoff-Fenster umgehen (#533): ein
                    # Ueberhitzungsfall ist per Definition kein Dauerzustand,
                    # und thermische Sicherheit schlaegt Log-Hygiene.
                    await self._backend.set_pwm(
                        fan.fan_id, target_pwm, force=(mode == FanMode.EMERGENCY)
                    )
                self._last_pwm_by_fan[fan.fan_id] = target_pwm

                if (
                    mode == FanMode.EMERGENCY
                    and config.mode != FanMode.EMERGENCY.value
                    and fan.pwm_control is not PwmControl.FIRMWARE_MANAGED
                    and not is_released(zustand)
                ):
                    # Bei firmware-verwalteten Lueftern brachte EMERGENCY nichts
                    # ausser einem Zustand, aus dem nur der AUTO-Button wieder
                    # herausfuehrt. Die Benachrichtigung oben bleibt erhalten.
                    config.mode = FanMode.EMERGENCY.value
                    db.commit()

                self._sample_buffer.append({
                    "timestamp": datetime.now(timezone.utc),
                    "fan_id": fan.fan_id,
                    "pwm_percent": target_pwm,
                    "rpm": fan.rpm,
                    "temperature_celsius": temperature,
                    "mode": mode.value,
                })

        # Nur bei echter Aenderung schreiben -- ein Schreibvorgang je Tick waere
        # dieselbe Sorte Last, die #533 beseitigt hat.
        if freigegeben != freigaben_vorher:
            with self.db_session_factory() as db:
                if publish_released_fans(db, freigegeben):
                    self._zuletzt_freigegeben = set(freigegeben)
                else:
                    # Scheitert der Schreibvorgang, darf der Stand NICHT als
                    # veroeffentlicht gelten: sonst haelte dieser Prozess den
                    # Kanal fuer freigegeben, waehrend die anderen Worker und
                    # der naechste Zyklus nichts davon wissen -- und die
                    # Zusage "Zustand statt Flanke" haenge an einem Write, der
                    # nicht stattgefunden hat.
                    logger.warning(
                        "Freigabe-Zustand nicht veroeffentlicht -- naechster "
                        "Zyklus versucht es erneut")

    def _apply_hysteresis(
        self,
        fan_id: str,
        temperature: float,
        hysteresis: float,
        target_pwm: int,
    ) -> int:
        """Daempft ein BEREITS BERECHNETES PWM-Ziel gegen Oszillation.

        Steigende Ziele greifen sofort (Sicherheit); fallende erst, wenn die
        Temperatur um `hysteresis` Grad unter den Wert gefallen ist, bei dem
        zuletzt geregelt wurde.

        #517: Der Vorgaenger rechnete das Ziel aus einer Kurve NEU — und bekam
        vom einzigen Aufrufer eine leere Liste, was den Hardcode 50 lieferte und
        das Ergebnis von evaluate_curve verwarf. Diese Funktion rechnet nichts
        mehr aus; die Kurvenauswertung gehoert allein fan_curve_eval.py.
        """
        current_time = time.time()

        if fan_id not in self._hysteresis_state:
            self._hysteresis_state[fan_id] = HysteresisState(
                last_pwm=target_pwm,
                last_pwm_temp=temperature,
                last_update=current_time,
            )
            return target_pwm

        state = self._hysteresis_state[fan_id]

        if target_pwm > state.last_pwm:
            # Temperatur steigt — sofort reagieren.
            state.last_pwm = target_pwm
            state.last_pwm_temp = temperature
            state.last_update = current_time
            return target_pwm

        if target_pwm < state.last_pwm:
            if temperature <= (state.last_pwm_temp - hysteresis):
                state.last_pwm = target_pwm
                state.last_pwm_temp = temperature
                state.last_update = current_time
                return target_pwm
            return state.last_pwm

        return state.last_pwm

    async def _persist_samples(self):
        """Persist buffered samples to database."""
        if not self._sample_buffer:
            return

        samples_to_save = list(self._sample_buffer)
        self._sample_buffer.clear()

        with self.db_session_factory() as db:
            for sample in samples_to_save:
                db_sample = FanSample(**sample)
                db.add(db_sample)

            db.commit()

        logger.debug(f"Persisted {len(samples_to_save)} fan sample(s)")

    async def get_status(self) -> Dict:
        """Get current fan status."""
        if not self._backend:
            return {
                "fans": [],
                "is_dev_mode": self.config.is_dev_mode,
                "is_using_linux_backend": self._use_linux_backend,
                "permission_status": "unavailable",
                "backend_available": False,
            }

        fans = await self._backend.get_fans()

        # Load configs from DB
        with self.db_session_factory() as db:
            fan_data_list = []

            for fan in fans:
                config = db.execute(
                    select(FanConfig).where(FanConfig.fan_id == fan.fan_id)
                ).scalar_one_or_none()

                if config:
                    curve_points = json.loads(config.curve_json) if config.curve_json else []

                    # Use config's temp sensor for display (may differ from scan sensor)
                    display_temp = fan.temperature_celsius
                    if config.temp_sensor_id:
                        try:
                            sensor_temp = await self._registry.get_temp(config.temp_sensor_id)
                            if sensor_temp is not None:
                                display_temp = sensor_temp
                        except Exception:
                            pass  # Keep fan.temperature_celsius as fallback

                    fan_entry = {
                        "fan_id": fan.fan_id,
                        "name": config.name,
                        "rpm": fan.rpm,
                        "pwm_percent": fan.pwm_percent,
                        "temperature_celsius": display_temp,
                        "mode": config.mode,
                        "is_active": config.is_active,
                        "min_pwm_percent": config.min_pwm_percent,
                        "max_pwm_percent": config.max_pwm_percent,
                        "emergency_temp_celsius": config.emergency_temp_celsius,
                        "temp_sensor_id": config.temp_sensor_id,
                        "curve_points": curve_points,
                        "hysteresis_celsius": getattr(config, 'hysteresis_celsius', 3.0),
                        "is_gpu_fan": fan.is_gpu_fan,
                        "gpu_vendor": fan.gpu_vendor,
                        "last_write_error": fan.last_write_error,
                        "pwm_control": fan.pwm_control,
                        "curve_type": getattr(config, "curve_type", "graph"),
                        "flat_pwm_percent": getattr(config, "flat_pwm_percent", None),
                        "target_temp_celsius": getattr(config, "target_temp_celsius", None),
                        "target_pwm_percent": getattr(config, "target_pwm_percent", None),
                        "mix_curve_a_id": getattr(config, "mix_curve_a_id", None),
                        "mix_curve_b_id": getattr(config, "mix_curve_b_id", None),
                        "mix_function": getattr(config, "mix_function", None),
                        "sync_fan_id": getattr(config, "sync_fan_id", None),
                        "start_pwm_percent": getattr(config, "start_pwm_percent", None),
                        "stop_below_temp_celsius": getattr(config, "stop_below_temp_celsius", None),
                        "response_time_seconds": getattr(config, "response_time_seconds", 0.0),
                        "pwm_steps": getattr(config, "pwm_steps", 1),
                    }

                    # Add schedule info for scheduled mode
                    if config.mode == FanMode.SCHEDULED.value:
                        _, active_entry = self._schedule.resolve_active_curve(
                            fan.fan_id, config.curve_json, db
                        )
                        if active_entry:
                            fan_entry["active_schedule"] = {
                                "id": active_entry.id,
                                "name": active_entry.name,
                                "start_time": active_entry.start_time,
                                "end_time": active_entry.end_time,
                            }

                    fan_data_list.append(fan_entry)
                else:
                    # No DB config yet (first discovery or hwmon index changed)
                    # Include with defaults so the fan isn't silently dropped
                    fan_data_list.append({
                        "fan_id": fan.fan_id,
                        "name": fan.name,
                        "rpm": fan.rpm,
                        "pwm_percent": fan.pwm_percent,
                        "temperature_celsius": fan.temperature_celsius,
                        "mode": FanMode.MANUAL.value,
                        "is_active": True,
                        "min_pwm_percent": 0,
                        "max_pwm_percent": 100,
                        "emergency_temp_celsius": 85.0,
                        "temp_sensor_id": fan.temp_sensor_id,
                        "curve_points": [],
                        "hysteresis_celsius": 3.0,
                        "is_gpu_fan": fan.is_gpu_fan,
                        "gpu_vendor": fan.gpu_vendor,
                        "last_write_error": fan.last_write_error,
                        "pwm_control": fan.pwm_control,
                        "curve_type": "graph",
                        "flat_pwm_percent": None,
                        "target_temp_celsius": None,
                        "target_pwm_percent": None,
                        "mix_curve_a_id": None,
                        "mix_curve_b_id": None,
                        "mix_function": None,
                        "sync_fan_id": None,
                        "start_pwm_percent": None,
                        "stop_below_temp_celsius": None,
                        "response_time_seconds": 0.0,
                        "pwm_steps": 1,
                    })

        # Den vom Primary gemeldeten Kanalzustand ueberlagern (#568 Punkt 2).
        # pwm_control lebt im _fan_cache des jeweiligen Workers, gesetzt wird
        # es aber nur von dem, der schreibt. Ohne diese Ueberlagerung meldeten
        # die drei Follower fuer denselben Kanal weiter `supported`, und das
        # Badge in der Karte erschiene und verschwaende im 5-Sekunden-Poll.
        gesperrt = None
        shared_permission = None
        if self._use_linux_backend:
            # Die erneute Probe gehoert auch hierher, nicht nur in den
            # Regelkreis (#568): der laeuft NUR im Primary. Ein Follower, der
            # ueber eine Nutzer-Eingabe ein EACCES gesehen hat, schreibt von
            # sich aus nie wieder -- sein NO_PERMISSION haette ohne diesen
            # Aufruf keinen Rueckweg ausser einem Dienst-Neustart. Dieselbe
            # Sackgasse wie beim globalen Flag, nur eine Ebene tiefer.
            #
            # Kein Lastproblem: die Methode taktet sich selbst auf hoechstens
            # einen Lauf je 60 s und ist ein No-op, solange geschrieben werden
            # darf -- im Normalbetrieb kostet sie einen Attributzugriff.
            erneut = getattr(self._backend, "recheck_write_permission", None)
            if erneut is not None:
                await erneut()
            # EINE Sitzung fuer beide Leser: sie holen dieselbe
            # Singleton-Zeile, und get_status() bedient sowohl
            # GET /api/fans/status als auch GET /api/fans/permissions -- im
            # 5-Sekunden-Poll je Client und Worker.
            with self.db_session_factory() as db:
                gesperrt = read_denied_fans(db)
                shared_permission = read_write_permission(db)
                freigegeben = read_released_fans(db)
            # Der Besitzzustand kommt ausschliesslich aus der gemeinsamen
            # Zeile (#534): er entsteht im Primary, und ein prozesslokaler
            # Wert lieferte bei drei von vier Workern None.
            for eintrag in fan_data_list:
                eintrag["ownership"] = freigegeben.get(
                    eintrag["fan_id"], FanOwnership.OWNED.value)
            if gesperrt is not None:
                for eintrag in fan_data_list:
                    if eintrag.get("pwm_control") is PwmControl.FIRMWARE_MANAGED:
                        # Eine dauerhafte Hardware-Eigenschaft. Sie darf von
                        # einem Laufzeit-Befund nicht ueberschrieben werden.
                        continue
                    if eintrag["fan_id"] in gesperrt:
                        eintrag["pwm_control"] = PwmControl.NO_PERMISSION
                    # KEINE Ruecknahme in der Gegenrichtung: eine
                    # Nutzer-Eingabe geht ueber irgendeinen Worker, und bei
                    # EACCES vermerkt genau DER den Kanal. Der Primary hat
                    # diesen Write nie versucht -- in MANUAL schreibt er gar
                    # nicht --, seine Liste kennt den Kanal also nicht. Wuerde
                    # die Ueberlagerung ihn deshalb auf SUPPORTED zuruecksetzen,
                    # verschwaende der frische Befund sofort wieder, und
                    # dieselbe Antwort truege `last_write_error` neben
                    # `pwm_control: supported` -- ein sich selbst
                    # widersprechender Payload. Vereinigung statt Ersetzung:
                    # zurueckgenommen wird ein NO_PERMISSION nur von dem
                    # Worker, der es gesetzt hat, durch einen eigenen
                    # erfolgreichen Write oder die eigene Probe.

        # Determine permission status
        permission_status = "ok"
        if self._use_linux_backend:
            if isinstance(self._backend, LinuxFanControlBackend):
                # Der veroeffentlichte Stand des Primary schlaegt die eigene
                # Messung: ein Follower schreibt im Regelbetrieb nie und
                # bleibt deshalb auf seinem Startwert stehen. Fehlt die
                # Zeile (frisch migriert), entscheidet die eigene Messung.
                may_write = (self._backend.has_write_permission()
                             if shared_permission is None else shared_permission)
                permission_status = "ok" if may_write else "readonly"

        return {
            "fans": fan_data_list,
            "is_dev_mode": self.config.is_dev_mode,
            "is_using_linux_backend": self._use_linux_backend,
            "permission_status": permission_status,
            "backend_available": True,
        }

    async def reacquire_fan(self, fan_id: str) -> bool:
        """Einen freigegebenen Kanal wieder uebernehmen (#534 Punkt 1).

        Der Rueckweg muss ausdruecklich existieren: eine Oberflaeche, die einen
        freigegebenen Luefter wie einen firmware-verwalteten sperrt, deaktiviert
        genau die Bedienelemente, ueber die man zurueckkaeme -- ein Zustand ohne
        Ausgang.

        Entfernt wird nur der veroeffentlichte Zustand. Den erzwungenen Write
        uebernimmt der naechste Regelzyklus: er sieht den Kanal wieder als
        besessen, und weil der Zaehler des Backoffs beim Freigeben nicht
        zurueckgesetzt wurde, faellt der Kanal bei anhaltendem Fehler nach einem
        weiteren Fehlschlag erneut heraus -- gewollt, sonst pendelte die
        Anzeige.

        Returns:
            False, wenn der Kanal gar nicht freigegeben war.
        """
        with self.db_session_factory() as db:
            freigegeben = read_released_fans(db)
            if fan_id not in freigegeben:
                return False
            del freigegeben[fan_id]
            publish_released_fans(db, freigegeben)

        # Der erzwungene Write und das Zuruecksetzen des Fehlerzaehlers
        # geschehen NICHT hier, sondern im naechsten Zyklus des Primary. Diese
        # Route laeuft auf einem beliebigen der vier Worker, und der Zaehler
        # lebt im Prozess: ein Reset hier traefe den falschen. Der Primary
        # erkennt die Wiederuebernahme daran, dass der Kanal aus der
        # veroeffentlichten Menge verschwunden ist (#534).
        logger.info("%s: Wiederuebernahme angefordert", fan_id)
        return True

    async def set_fan_mode(self, fan_id: str, mode: FanMode) -> bool:
        """Set fan operation mode."""
        with self.db_session_factory() as db:
            config = db.execute(
                select(FanConfig).where(FanConfig.fan_id == fan_id)
            ).scalar_one_or_none()

            if not config:
                logger.warning(f"Fan config not found: {fan_id}")
                return False

            config.mode = mode.value
            db.commit()

        logger.info(f"Set {fan_id} mode to {mode.value}")
        return True

    async def set_fan_pwm(self, fan_id: str, pwm_percent: int) -> Tuple[bool, Optional[int]]:
        """Set manual PWM value."""
        if not self._backend:
            return False, None

        # Check if in manual mode
        with self.db_session_factory() as db:
            config = db.execute(
                select(FanConfig).where(FanConfig.fan_id == fan_id)
            ).scalar_one_or_none()

            if not config:
                return False, None

            if config.mode != FanMode.MANUAL.value:
                logger.warning(f"Cannot set PWM for {fan_id} in {config.mode} mode")
                return False, None

            # Apply min/max limits
            pwm_percent = max(config.min_pwm_percent, min(config.max_pwm_percent, pwm_percent))

        # Set PWM. Nutzeraktion: das Backoff-Fenster umgehen (#533), damit der
        # Klick einen echten Versuch und eine echte Fehlermeldung bekommt.
        success = await self._backend.set_pwm(fan_id, pwm_percent, force=True)

        # Read back RPM
        rpm = None
        if success:
            fans = await self._backend.get_fans()
            for fan in fans:
                if fan.fan_id == fan_id:
                    rpm = fan.rpm
                    break

        return success, rpm

    async def update_fan_curve(self, fan_id: str, curve_points: List[FanCurvePoint]) -> bool:
        """Update fan temperature curve."""
        with self.db_session_factory() as db:
            config = db.execute(
                select(FanConfig).where(FanConfig.fan_id == fan_id)
            ).scalar_one_or_none()

            if not config:
                return False

            # Serialize curve
            curve_json = json.dumps([p.model_dump() for p in curve_points])
            config.curve_json = curve_json
            db.commit()

        logger.info(f"Updated curve for {fan_id} with {len(curve_points)} point(s)")
        return True

    async def get_available_temp_sensors(self) -> List["TempSensorData"]:
        """Get all available temperature sensors from the backend."""
        if not self._backend:
            return []
        return await self._backend.get_available_temp_sensors()

    async def get_history(
        self,
        fan_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[FanSample], int]:
        """Get historical fan samples."""
        with self.db_session_factory() as db:
            query = select(FanSample)

            if fan_id:
                query = query.where(FanSample.fan_id == fan_id)

            # Get total count
            count_query = select(FanSample)
            if fan_id:
                count_query = count_query.where(FanSample.fan_id == fan_id)
            total_count = db.execute(select(func.count()).select_from(count_query.subquery())).scalar()

            # Get samples
            query = query.order_by(desc(FanSample.timestamp)).limit(limit).offset(offset)
            samples = db.execute(query).scalars().all()

            return list(samples), total_count or 0

    async def switch_backend(self, use_linux: bool) -> Tuple[bool, bool]:
        """
        Switch between Linux and dev backend.

        Returns:
            (success, is_using_linux_backend)
        """
        async with self._lifecycle_lock:
            # Gleiche Reihenfolge wie in stop(): erst die Schleife stilllegen,
            # dann zurueckgeben, dann tauschen. Ohne das schriebe die
            # weiterlaufende Schleife pwm_enable=1 gegen die Rueckgabe, und ein
            # Wechsel auf das Dev-Backend liesse jeden Kanal in Handsteuerung
            # zurueck -- niemand regelt, ueber einen Admin-Endpunkt (#534).
            was_running = self._is_running
            await self._cancel_monitoring_task()
            try:
                await self._release_all_to_board()
            except Exception:
                logger.exception("Rueckgabe beim Backend-Wechsel fehlgeschlagen")

            try:
                if use_linux:
                    # Try to switch to Linux backend
                    linux_backend = LinuxFanControlBackend(self.config)
                    if await linux_backend.is_available():
                        self._backend = linux_backend
                        self._use_linux_backend = True
                        await self._load_fan_configs()
                        logger.info("Switched to Linux fan control backend")
                        result = True, True
                    else:
                        logger.warning("Linux backend not available")
                        result = False, self._use_linux_backend
                else:
                    # Switch to dev backend
                    self._backend = DevFanControlBackend(self.config)
                    self._use_linux_backend = False
                    await self._load_fan_configs()
                    logger.info("Switched to dev fan control backend")
                    result = True, False
            finally:
                # Der Neustart gehoert ins finally: zwischen Abbruch (oben)
                # und hier koennen is_available() und _load_fan_configs()
                # werfen. Ohne das bliebe die Regelung nach einem
                # gescheiterten Wechsel bis zum Prozess-Neustart still stehen
                # -- schlimmer als der Zustand, den dieser Wechsel beheben
                # sollte.
                if was_running:
                    self._start_monitoring_task()

            return result

    # --- Delegating methods for backward compatibility ---

    async def get_schedule_entries(self, fan_id: str):
        return await self._schedule.get_schedule_entries(fan_id)

    async def create_schedule_entry(self, fan_id: str, name: str, start_time: str, end_time: str, **kwargs):
        return await self._schedule.create_schedule_entry(fan_id, name, start_time, end_time, **kwargs)

    async def update_schedule_entry(self, fan_id: str, entry_id: int, **kwargs):
        return await self._schedule.update_schedule_entry(fan_id, entry_id, **kwargs)

    async def delete_schedule_entry(self, fan_id: str, entry_id: int) -> bool:
        return await self._schedule.delete_schedule_entry(fan_id, entry_id)

    async def get_active_schedule_entry(self, fan_id: str):
        return await self._schedule.get_active_schedule_entry(fan_id)

    async def list_profiles(self):
        return await self._profiles.list_profiles()

    async def get_profile(self, profile_id: int):
        return await self._profiles.get_profile(profile_id)

    async def create_profile(self, name: str, curve_points, description=None):
        return await self._profiles.create_profile(name, curve_points, description)

    async def update_profile(self, profile_id: int, **kwargs):
        return await self._profiles.update_profile(profile_id, **kwargs)

    async def delete_profile(self, profile_id: int) -> bool:
        return await self._profiles.delete_profile(profile_id)

    async def apply_profile_to_fan(self, fan_id: str, profile_id: int):
        result = await self._profiles.apply_profile_to_fan(fan_id, profile_id)
        if result[0] and fan_id in self._hysteresis_state:
            del self._hysteresis_state[fan_id]
        return result

    async def apply_preset(self, fan_id: str, preset_name: str):
        result = await self._profiles.apply_preset(fan_id, preset_name)
        if result[0] and fan_id in self._hysteresis_state:
            del self._hysteresis_state[fan_id]
        return result

    async def update_fan_config(
        self,
        fan_id: str,
        hysteresis_celsius: Optional[float] = None,
        min_pwm_percent: Optional[int] = None,
        max_pwm_percent: Optional[int] = None,
        emergency_temp_celsius: Optional[float] = None,
        temp_sensor_id: Optional[str] = None,
        curve_type: Optional[str] = None,
        flat_pwm_percent: Optional[int] = None,
        target_temp_celsius: Optional[float] = None,
        target_pwm_percent: Optional[int] = None,
        mix_curve_a_id: Optional[int] = None,
        mix_curve_b_id: Optional[int] = None,
        mix_function: Optional[str] = None,
        sync_fan_id: Optional[str] = None,
        start_pwm_percent: Optional[int] = None,
        stop_below_temp_celsius: Optional[float] = None,
        response_time_seconds: Optional[float] = None,
        pwm_steps: Optional[int] = None,
    ) -> Optional[Dict]:
        """
        Update fan configuration.

        Args:
            fan_id: Fan identifier
            hysteresis_celsius: Temperature hysteresis (0-15°C)
            min_pwm_percent: Minimum PWM percentage
            max_pwm_percent: Maximum PWM percentage
            emergency_temp_celsius: Emergency temperature threshold
            temp_sensor_id: Temperature sensor to use for this fan
            curve_type: Curve type (graph|flat|target|mix|sync)
            flat_pwm_percent: Fixed PWM percent for flat curve type
            target_temp_celsius: Target temperature for target curve type
            target_pwm_percent: Target PWM percent for target curve type
            mix_curve_a_id: First profile ID for mix curve type
            mix_curve_b_id: Second profile ID for mix curve type
            mix_function: Mix function (max|sum)
            sync_fan_id: Fan ID to sync with for sync curve type
            start_pwm_percent: Minimum PWM at fan start
            stop_below_temp_celsius: Temperature below which fan stops
            response_time_seconds: PWM response time in seconds (0-60)
            pwm_steps: PWM step size (1, 5, 10, or 25)

        Returns:
            Updated configuration dict or None if fan not found
        """
        with self.db_session_factory() as db:
            config = db.execute(
                select(FanConfig).where(FanConfig.fan_id == fan_id)
            ).scalar_one_or_none()

            if not config:
                return None

            # Update provided values
            if hysteresis_celsius is not None:
                config.hysteresis_celsius = hysteresis_celsius
                # Clear hysteresis state when hysteresis value changes
                if fan_id in self._hysteresis_state:
                    del self._hysteresis_state[fan_id]

            if min_pwm_percent is not None:
                config.min_pwm_percent = min_pwm_percent

            if max_pwm_percent is not None:
                config.max_pwm_percent = max_pwm_percent

            if emergency_temp_celsius is not None:
                config.emergency_temp_celsius = emergency_temp_celsius

            if temp_sensor_id is not None:
                config.temp_sensor_id = temp_sensor_id

            if curve_type is not None:
                config.curve_type = curve_type

            if flat_pwm_percent is not None:
                config.flat_pwm_percent = flat_pwm_percent

            if target_temp_celsius is not None:
                config.target_temp_celsius = target_temp_celsius

            if target_pwm_percent is not None:
                config.target_pwm_percent = target_pwm_percent

            if mix_curve_a_id is not None:
                config.mix_curve_a_id = mix_curve_a_id

            if mix_curve_b_id is not None:
                config.mix_curve_b_id = mix_curve_b_id

            if mix_function is not None:
                config.mix_function = mix_function

            if sync_fan_id is not None:
                config.sync_fan_id = sync_fan_id

            if start_pwm_percent is not None:
                config.start_pwm_percent = start_pwm_percent

            if stop_below_temp_celsius is not None:
                config.stop_below_temp_celsius = stop_below_temp_celsius

            if response_time_seconds is not None:
                config.response_time_seconds = response_time_seconds

            if pwm_steps is not None:
                config.pwm_steps = pwm_steps

            db.commit()

            logger.info(f"Updated config for {fan_id}: hysteresis={config.hysteresis_celsius}°C, curve_type={config.curve_type}")

            return {
                "fan_id": fan_id,
                "hysteresis_celsius": config.hysteresis_celsius,
                "min_pwm_percent": config.min_pwm_percent,
                "max_pwm_percent": config.max_pwm_percent,
                "emergency_temp_celsius": config.emergency_temp_celsius,
                "temp_sensor_id": config.temp_sensor_id,
                "curve_type": config.curve_type,
                "flat_pwm_percent": config.flat_pwm_percent,
                "target_temp_celsius": config.target_temp_celsius,
                "target_pwm_percent": config.target_pwm_percent,
                "mix_curve_a_id": config.mix_curve_a_id,
                "mix_curve_b_id": config.mix_curve_b_id,
                "mix_function": config.mix_function,
                "sync_fan_id": config.sync_fan_id,
                "start_pwm_percent": config.start_pwm_percent,
                "stop_below_temp_celsius": config.stop_below_temp_celsius,
                "response_time_seconds": config.response_time_seconds,
                "pwm_steps": config.pwm_steps,
            }


# Global service instance
_fan_control_service: Optional[FanControlService] = None


def get_fan_control_service() -> FanControlService:
    """Get the singleton FanControlService instance."""
    global _fan_control_service
    if _fan_control_service is None:
        from app.core.config import get_settings
        from app.core.database import SessionLocal
        settings = get_settings()
        _fan_control_service = FanControlService(settings, SessionLocal)
    return _fan_control_service


async def start_fan_control(monitoring: bool = True) -> None:
    """Start the fan control service.

    Args:
        monitoring: If True, start the monitoring loop (primary worker).
                    If False, only initialize backend + configs (secondary workers).
    """
    service = get_fan_control_service()
    await service.start(monitoring=monitoring)


async def stop_fan_control() -> None:
    """Stop the fan control service."""
    global _fan_control_service
    if _fan_control_service is not None:
        await _fan_control_service.stop()
        _fan_control_service = None


def get_service_status() -> dict:
    """
    Get fan control service status for admin dashboard.

    Returns:
        Dict with service status information
    """
    from app.core.config import get_settings

    settings = get_settings()

    if _fan_control_service is None:
        return {
            "is_running": False,
            "started_at": None,
            "uptime_seconds": None,
            "sample_count": 0,
            "error_count": 0,
            "last_error": None,
            "last_error_at": None,
            "interval_seconds": settings.fan_sample_interval_seconds,
            "config_enabled": settings.fan_control_enabled,
        }

    service = _fan_control_service
    is_running = service._is_running and service._monitoring_task is not None

    return {
        "is_running": is_running,
        "started_at": None,  # Not tracked by fan control service
        "uptime_seconds": None,
        "sample_count": len(service._sample_buffer),
        "error_count": 0,  # Not tracked separately
        "last_error": None,
        "last_error_at": None,
        "interval_seconds": service.config.fan_sample_interval_seconds,
        "config_enabled": service.config.fan_control_enabled,
        "backend_type": "linux" if service._use_linux_backend else "dev",
    }
