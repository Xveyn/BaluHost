"""
Linux hardware backend for fan control using hwmon sysfs.
"""
import errno
import getpass
import logging
import re
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.core.config import Settings
from app.schemas.fans import FanMode, FanCurvePoint, PwmControl
from app.services.power.fan_control import FanControlBackend, FanData, TempSensorData
from app.services.power.fan_gpu_manual import probe_amd_pwm_control
from app.services.power.fan_identity import (
    build_fan_id,
    build_sensor_id,
    derive_all,
)

logger = logging.getLogger(__name__)


def _by_leading_number(path: Path) -> Tuple[int, str]:
    """Sortierschluessel fuer hwmon-Eintraege: numerisch, nicht lexikografisch.

    Ein blosses sorted() stellte "hwmon10" vor "hwmon2" und "temp10_input" vor
    "temp1_input" -- deterministisch, aber falsch. Auf dem nct6798 traegt der
    Chip temp1..temp13, und temp10 ist PCH_CHIP_TEMP mit Messwert 0; als
    Fallback-Kurvenquelle waere das eine tote Zahl (#553).
    """
    match = re.search(r"\d+", path.name)
    return (int(match.group()) if match else -1, path.name)


FIRMWARE_MANAGED_WRITE_ERROR = (
    "This GPU manages its fan curve in firmware (RDNA3+). The amdgpu driver "
    "does not support live PWM control on this card — setting "
    "amdgpu.ppfeaturemask=0xffffffff does NOT change that. Control is only "
    "possible through the firmware curve (gpu_od/fan_ctrl), see issue #516."
)

# Backoff gegen Knoten, die den Write dauerhaft ablehnen (#533). Der Regelkreis
# laeuft alle 5 s; ohne Deckelung ergab das 17k Logzeilen und 34k sudo-Aufrufe
# pro Tag fuer einen einzigen Luefter.
#
# Die Basis ist BEWUSST groesser als ein Regelzyklus: mit 5 s waere das erste
# Fenster genau einen Zyklus lang und wuerde nichts unterdruecken.
PWM_BACKOFF_BASE_SECONDS = 10.0
PWM_BACKOFF_MAX_SECONDS = 900.0  # 15 Minuten


class LinuxFanControlBackend(FanControlBackend):
    """Linux hardware backend using hwmon sysfs."""

    # Abstand zwischen zwei Rechte-Proben, wenn die Ableitung `readonly`
    # sagt. Lang genug, dass ein dauerhaft rechteloser Zustand keine Last
    # erzeugt, kurz genug, dass eine reparierte Rechtelage von selbst
    # zurueckfindet (#568).
    _PERMISSION_RECHECK_SECONDS = 60.0

    def __init__(self, config: Settings):
        self.config = config
        self._hwmon_base = Path("/sys/class/hwmon")
        self._fan_cache: Dict[str, Dict] = {}
        self._has_write_permission = False
        # fan_id -> (fail_count, naechster erlaubter Versuch als monotone Zeit).
        # Bewusst NICHT in _fan_cache: der wird bei jedem Rescan neu gebaut,
        # der Backoff muss das ueberleben.
        self._write_backoff: Dict[str, Tuple[int, float]] = {}
        # Fruehestens erlaubter Zeitpunkt der naechsten Rechte-Probe (#568).
        self._next_permission_recheck: float = 0.0
        # Ergebnis der letzten Probe -- nur fuer die Log-Hygiene: die
        # Probe laeuft periodisch, gemeldet wird nur der Wechsel (#568).
        self._letzte_probe_erfolgreich: Optional[bool] = None
        # Rueckabbildung stabile Sensor-Kennung -> tempN_input-Pfad. Ohne sie
        # kann get_temperature() die ID nicht mehr aufloesen, weil sie nicht
        # mehr aus dem hwmon-Verzeichnisnamen besteht (#532).
        self._temp_paths: Dict[str, Path] = {}
        self._monotonic = time.monotonic

    async def is_available(self) -> bool:
        """Check if hwmon is available."""
        if not self._hwmon_base.exists():
            logger.info("hwmon not available (not on Linux or no sensors)")
            return False

        # Scan for PWM fans
        fans = await self._scan_pwm_fans()
        if not fans:
            logger.info("No PWM fans found in hwmon")
            return False

        logger.info(f"Found {len(fans)} PWM fan(s) in hwmon")
        await self._check_write_permission()
        return True

    async def _check_write_permission(self) -> None:
        """Prueft Schreibrechte auf dem Weg, den set_pwm tatsaechlich nimmt.

        Geschrieben wird pwm_enable mit dem Wert, der dort bereits steht:
        dieselbe Datei, dieselben Rechte und dieselbe sudoers-Regel wie im
        Regelbetrieb -- aber ohne den Modus zu veraendern.

        pwm selbst taugt nicht als Probe. Der nct6775 lehnt pwm-Writes mit
        EBUSY ab, solange pwm_enable >= 2 steht, und seit der Rueckgabe an
        die Board-Automatik (#534) steht nach jedem Dienst-Ende genau das
        an. Ein pwm_enable=1, wie set_pwm es setzt, waere umgekehrt ein
        echter Eingriff als Nebenwirkung einer Frage.

        Geprueft werden alle Kanaele statt nur des ersten: Schreibrecht
        besteht, sobald EIN steuerbarer Luefter beschreibbar ist. Der erste
        Cache-Eintrag ist auf dieser Hardware der firmware-verwaltete
        GPU-Luefter, den set_pwm gar nicht anfasst -- ueber unsere
        Schreibfaehigkeit sagt er nichts aus (#552).
        """
        erster_erfolg = None
        for fan_id, fan_info in self._fan_cache.items():
            if fan_info.get("pwm_control") is PwmControl.FIRMWARE_MANAGED:
                continue

            # Fehlt das Modus-Register, bleibt nur der Duty-Knoten -- ohne
            # Automatik kann der auch kein EBUSY liefern.
            probe_path = fan_info.get("pwm_enable_path") or fan_info.get("pwm_path")
            if probe_path is None:
                continue

            current = await self._read_hwmon_file(probe_path)
            if current is None:
                continue

            ok, _ = await self._write_hwmon_file(probe_path, str(current))
            if ok:
                self._has_write_permission = True
                # Auch den Kanalzustand zuruecknehmen (#568): sonst bliebe die
                # Ableitung in has_write_permission() auf NO_PERMISSION stehen,
                # obwohl die Probe gerade bewiesen hat, dass geschrieben werden
                # darf.
                if fan_info.get("pwm_control") is PwmControl.NO_PERMISSION:
                    fan_info["pwm_control"] = PwmControl.SUPPORTED
                    fan_info["last_write_error"] = None
                if erster_erfolg is None:
                    erster_erfolg = fan_id

        # KEIN frueher Ausstieg nach dem ersten Erfolg: bis #568 kehrte die
        # Probe dort zurueck, und die Kanaele dahinter blieben auf ihrem alten
        # NO_PERMISSION stehen. Solange das nur der Primary sah, war es ein
        # Schoenheitsfehler; seit der Kanalzustand an alle Worker verteilt wird,
        # behauptete es dauerhaft "kein Schreibrecht" auf funktionierenden
        # Kanaelen -- und in MANUAL raeumt kein set_pwm das je auf.
        if erster_erfolg is not None:
            if not self._letzte_probe_erfolgreich:
                logger.info(
                    f"Fan control: write permission available ({erster_erfolg})")
            self._letzte_probe_erfolgreich = True
            return

        # Nur beim Wechsel loggen: die Probe laeuft jetzt periodisch, eine
        # Zeile je Lauf waere 1440 am Tag -- dieselbe Sorte Rauschen, die #533
        # beseitigt hat.
        if self._letzte_probe_erfolgreich is not False:
            logger.info("Fan control: no write permission (readonly mode)")
        self._letzte_probe_erfolgreich = False

    def write_failure_state(self, fan_id: str) -> Tuple[int, bool]:
        """Wie oft der Regelkreis auf diesem Kanal nacheinander gescheitert ist.

        Returns:
            (fail_count, at_cap). `at_cap` heisst: das Backoff-Fenster ist auf
            PWM_BACKOFF_MAX_SECONDS gedeckelt, der Kanal lehnt also seit acht
            aufeinanderfolgenden Versuchen ab (mit den heutigen Konstanten).

        Ohne diesen Zugriff waere die Rueckgabe-Entscheidung aus #534 nicht
        formulierbar: `_write_backoff` ist privat, das aktuelle Fenster wird
        nicht gespeichert, und ein Aufrufer muesste den Deckel aus fail_count
        nachrechnen -- eine Verdopplung der Backoff-Formel an einer zweiten
        Stelle.
        """
        fail_count = self._write_backoff.get(fan_id, (0, 0.0))[0]
        if fail_count <= 0:
            return 0, False
        fenster = PWM_BACKOFF_BASE_SECONDS * (2 ** (fail_count - 1))
        return fail_count, fenster >= PWM_BACKOFF_MAX_SECONDS

    async def recheck_write_permission(self) -> None:
        """Die Probe erneut fahren, wenn die Ableitung gerade `readonly` sagt.

        Ohne das kann sich der abgeleitete Zustand FESTSETZEN. Geheilt wird er
        nur ueber einen erfolgreichen Write, und den loest im Regelbetrieb
        allein der Regelkreis aus -- der einen Luefter im MANUAL-Modus nie
        schreibt (Ziel == Ist, siehe fan_control._apply_fan_curve). Sind die
        Rechte weg, meldet die Anzeige `readonly` und SPERRT die
        Bedienelemente; damit faellt auch der einzige verbliebene Schreibweg
        weg, die HTTP-Route. Der Nutzer kaeme ohne Dienst-Neustart nicht mehr
        heraus -- ein lauter Fehler statt des behobenen stillen, und ein
        schlechterer Tausch.

        Die Probe schreibt pwm_enable mit dem Wert, der dort bereits steht, ist
        also kein Eingriff. Sie laeuft hoechstens alle
        `_PERMISSION_RECHECK_SECONDS`, damit ein dauerhaft rechteloser Zustand
        nicht jeden Regelzyklus einen Schreibversuch je Kanal ausloest.
        """
        if self.has_write_permission():
            return
        jetzt = self._monotonic()
        if jetzt < self._next_permission_recheck:
            return
        self._next_permission_recheck = jetzt + self._PERMISSION_RECHECK_SECONDS
        await self._check_write_permission()

    def has_write_permission(self) -> bool:
        """Ob BaluHost derzeit ueberhaupt einen Luefter schreiben kann.

        `_has_write_permission` allein taugt dafuer nicht: es wird auf True
        gesetzt (Probe beim Start, erfolgreicher Write) und von NIEMANDEM auf
        False zurueck (#568 Punkt 1). Gingen die Rechte zur Laufzeit verloren
        -- eine udev-Regel, die nach einem Treiber-Reload nicht mehr greift,
        eine sudoers-Aenderung, die die Box nie erreicht hat --, meldete
        `GET /api/fans/permissions` weiter `ok`, waehrend nichts mehr
        geschrieben wurde. Die Bedienelemente blieben frei und jede Eingabe
        verpuffte.

        Abgeleitet wird deshalb aus dem Zustand je Kanal, den set_pwm ohnehin
        pflegt: NO_PERMISSION bei beobachtetem EACCES/EPERM, zurueck auf
        SUPPORTED nach dem naechsten erfolgreichen Write.

        NICHT am Backoff aus #533 aufgehaengt, obwohl das Issue es vorschlaegt:
        die Sperre zaehlt Fehlschlaege jeder Art, auch EINVAL vom Treiber. Das
        waere eine Aussage ueber "der Write klappt nicht", nicht ueber "wir
        duerfen nicht" -- und die Rechteanzeige soll das zweite sagen.

        Der Geltungsbereich ist bewusst global-restriktiv: ein einzelner
        gesperrter Kanal macht die Steuerung nicht tot (auf dieser Hardware ist
        genau ein Kanal firmware-verwaltet und vier sind steuerbar). Erst wenn
        JEDER steuerbare Kanal ein EACCES gesehen hat, ist die Anzeige
        `readonly`. Was einzelne Kanaele betrifft, zeigt die Karte je Luefter
        (#568 Punkt 2).
        """
        if not self._has_write_permission:
            return False

        steuerbar = [
            info for info in self._fan_cache.values()
            if info.get("pwm_control") is not PwmControl.FIRMWARE_MANAGED
        ]
        if not steuerbar:
            # Nichts Steuerbares erkannt: die Frage stellt sich nicht, und der
            # Startwert der Probe ist die beste vorhandene Aussage.
            return self._has_write_permission

        return any(
            info.get("pwm_control") is not PwmControl.NO_PERMISSION
            for info in steuerbar
        )

    async def get_fans(self) -> List[FanData]:
        """Get hardware fans from hwmon (uses cache from startup scan)."""

        fans = []
        for fan_id, fan_info in self._fan_cache.items():
            # Read current state
            pwm_value = await self._read_hwmon_file(fan_info["pwm_path"])
            pwm_percent = self._pwm_to_percent(pwm_value) if pwm_value is not None else 0

            rpm_value = await self._read_hwmon_file(fan_info["fan_input_path"])
            rpm = int(rpm_value) if rpm_value is not None else None

            temp_celsius = None
            if fan_info.get("temp_path"):
                temp_value = await self._read_hwmon_file(fan_info["temp_path"])
                if temp_value is not None:
                    temp_celsius = float(temp_value) / 1000.0  # millidegrees to degrees

            fans.append(FanData(
                fan_id=fan_id,
                name=fan_info["name"],
                rpm=rpm,
                pwm_percent=pwm_percent,
                temperature_celsius=temp_celsius,
                mode=FanMode.AUTO,  # Will be overridden by service from DB
                min_pwm_percent=self.config.fan_min_pwm_percent,
                max_pwm_percent=100,
                emergency_temp_celsius=self.config.fan_emergency_temp_celsius,
                temp_sensor_id=fan_info.get("temp_sensor_id"),
                curve_points=self._get_default_curve(),
                is_active=True,
                is_gpu_fan=fan_info.get("is_gpu_fan", False),
                gpu_vendor=fan_info.get("gpu_vendor"),
                device_driver=fan_info.get("device_driver"),
                last_write_error=fan_info.get("last_write_error"),
                pwm_control=fan_info.get("pwm_control", PwmControl.SUPPORTED),
            ))

        return fans

    async def set_pwm(self, fan_id: str, pwm_percent: int, force: bool = False) -> bool:
        """Set hardware PWM value.

        force=True umgeht das Backoff-Fenster (#533) — fuer Nutzeraktionen und
        den Notfallpfad, die einen echten Versuch und eine echte Fehlermeldung
        verdienen statt eines stillen False.
        """
        if fan_id not in self._fan_cache:
            logger.warning(f"Fan {fan_id} not found in cache")
            return False

        fan_info = self._fan_cache[fan_id]

        # Firmware besitzt die Kurve: sysfs gar nicht erst anfassen.
        if fan_info.get("pwm_control") is PwmControl.FIRMWARE_MANAGED:
            fan_info["last_write_error"] = FIRMWARE_MANAGED_WRITE_ERROR
            logger.debug(f"{fan_id}: firmware-managed fan curve, PWM write skipped")
            return False

        backoff = self._write_backoff.get(fan_id)
        if backoff is not None and not force and self._monotonic() < backoff[1]:
            logger.debug(
                f"{fan_id}: PWM write suppressed, {backoff[0]} consecutive failures, "
                f"retry in {backoff[1] - self._monotonic():.0f}s"
            )
            return False

        pwm_path = fan_info["pwm_path"]
        pwm_enable_path = fan_info.get("pwm_enable_path")

        pwm_percent = max(0, min(100, pwm_percent))
        pwm_value = self._percent_to_pwm(pwm_percent)

        if pwm_enable_path:
            ok_enable, _ = await self._write_hwmon_file(pwm_enable_path, "1")
            if not ok_enable:
                # DEBUG statt WARNING (#533): schlaegt pwm_enable fehl, schlaegt
                # gleich darauf auch der pwm-Write fehl und traegt die volle
                # Diagnose. Eine Zeile pro Episode, nicht zwei pro Zyklus.
                logger.debug(f"Failed to set PWM enable for {fan_id}")

        success, err_code = await self._write_hwmon_file(pwm_path, str(pwm_value))
        if success:
            fan_info["last_write_error"] = None
            recovered = self._write_backoff.pop(fan_id, None)
            if recovered is not None:
                logger.info(
                    f"{fan_id}: PWM write succeeded again after {recovered[0]} "
                    f"consecutive failure(s)"
                )
            if fan_info.get("pwm_control") is PwmControl.NO_PERMISSION:
                # Rechte wurden zur Laufzeit korrigiert.
                fan_info["pwm_control"] = PwmControl.SUPPORTED
            logger.debug(f"Set {fan_id} PWM to {pwm_percent}% ({pwm_value}/255)")
            return True

        if err_code in (errno.EACCES, errno.EPERM):
            fan_info["pwm_control"] = PwmControl.NO_PERMISSION
            try:
                user = getpass.getuser()
            except Exception:
                user = "the service user"
            fan_info["last_write_error"] = (
                f"No write permission for {pwm_path} "
                f"({errno.errorcode.get(err_code, err_code)}). The backend runs as "
                f"'{user}' and the udev rule does not cover hwmon PWM nodes."
            )
        elif err_code is None:
            # _write_hwmon_file() found the path missing before even attempting
            # the write — the kernel rejected nothing, the sysfs node is gone
            # (device removed or driver reloaded). Do not claim a kernel
            # rejection that never happened.
            fan_info["last_write_error"] = (
                f"PWM sysfs node {pwm_path} no longer exists (device removed "
                f"or driver reloaded)."
            )
        else:
            driver = fan_info.get("device_driver", "unknown")
            enable_val = None
            if pwm_enable_path:
                v = await self._read_hwmon_file(pwm_enable_path)
                enable_val = v if v is not None else "?"
            fan_info["last_write_error"] = (
                f"PWM write rejected by kernel (driver={driver}, "
                f"pwm_enable={enable_val}, "
                f"errno={errno.errorcode.get(err_code, err_code)})."
            )

        if force:
            # Erzwungene Writes zaehlen nicht ins Backoff (#534): der Zaehler
            # traegt seit #568 eine zweite Bedeutung -- am Deckel gilt ein Kanal
            # als nicht steuerbar und wird an die Board-Automatik
            # zurueckgegeben. Acht erfolglose Nutzer-Klicks (oder Notfall-Writes)
            # duerfen den Luefter nicht abgeben; gezaehlt wird nur, was der
            # Regelkreis von sich aus versucht hat.
            #
            # Gemeldet wird trotzdem, und zwar als ERROR: ein erzwungener
            # Write kommt von einer Nutzeraktion oder aus dem Notfall -- beide
            # will man im Log sehen, unabhaengig davon, ob der Zaehler laeuft.
            # Fuer die Log-Hygiene aus #533 ist das unschaedlich: erzwungene
            # Writes sind selten und umgehen das Fenster ohnehin.
            logger.error(
                f"{fan_id}: erzwungener PWM-Write fehlgeschlagen -- "
                f"{fan_info.get('last_write_error')}"
            )
            return False

        fail_count = self._write_backoff.get(fan_id, (0, 0.0))[0] + 1
        delay = min(
            PWM_BACKOFF_BASE_SECONDS * (2 ** (fail_count - 1)),
            PWM_BACKOFF_MAX_SECONDS,
        )
        self._write_backoff[fan_id] = (fail_count, self._monotonic() + delay)

        if fail_count == 1:
            # Erster Fehlschlag einer Episode: eine ERROR-Zeile mit der vollen
            # Diagnose. Wiederholungen laufen auf DEBUG, damit Fehler-Metrik und
            # Log-Alerting brauchbar bleiben.
            logger.error(
                f"Failed to write PWM for {fan_id}: {fan_info['last_write_error']} "
                f"Further attempts suppressed, next retry in {delay:.0f}s."
            )
        else:
            logger.debug(
                f"Failed to write PWM for {fan_id} ({fail_count} consecutive), "
                f"next retry in {delay:.0f}s"
            )
        return False

    async def release_to_board(self, fan_id: str, enable_value: int) -> bool:
        """Gibt die Regelung dieses Kanals an die Chip-Automatik zurueck.

        Umgeht das Write-Backoff aus #533 bewusst: dessen Sperre sitzt in
        set_pwm, nicht hier. Ein Kanal mit Schreibfehlern ist genau der, bei dem
        eine abgeschaltete Board-Automatik am meisten weh tut.
        """
        fan_info = self._fan_cache.get(fan_id)
        if fan_info is None:
            logger.warning(f"Rueckgabe fuer unbekannten Luefter {fan_id}")
            return False

        pwm_enable_path = fan_info.get("pwm_enable_path")
        if pwm_enable_path is None:
            return False

        driver = fan_info.get("device_driver", "unknown")
        ok, err_code = await self._write_hwmon_file(pwm_enable_path, str(enable_value))
        if not ok:
            # Achtung bei der Formulierung: _write_hwmon_file meldet nach einem
            # gescheiterten sudo-tee-Fallback EACCES, auch wenn der Kernel
            # eigentlich EINVAL geliefert hat (etwa weil check_trip_points()
            # nicht-monotone BIOS-Stuetzstellen gefunden hat). Der errno wird
            # deshalb genannt, aber nicht gedeutet.
            logger.warning(
                f"Rueckgabe an die Board-Automatik fehlgeschlagen: {fan_id} "
                f"(driver={driver}, Ziel={enable_value}, errno={err_code}). "
                f"Der Luefter bleibt in Handsteuerung -- es regelt niemand."
            )
            return False

        readback = await self._read_hwmon_file(pwm_enable_path)
        if readback != enable_value:
            logger.warning(
                f"Rueckgabe an die Board-Automatik ohne Wirkung: {fan_id} "
                f"(driver={driver}, geschrieben={enable_value}, "
                f"gelesen={readback}). Der Write wurde stillschweigend "
                f"verworfen."
            )
            return False

        logger.info(f"{fan_id}: an die Board-Automatik zurueckgegeben (pwm_enable={enable_value})")
        return True

    # CPU temperature driver names (same keywords as hardware/sensors.py)
    _CPU_SENSOR_DRIVERS = {"k10temp", "coretemp", "cpu_thermal", "acpi"}

    async def get_temperature(self, sensor_id: str) -> Optional[float]:
        """Get temperature from hwmon sensor.

        Loest zuerst ueber die Rueckabbildung aus dem Scan auf (stabile
        Kennungen, #532) und faellt danach auf die Altform hwmon<N>_temp<M>
        zurueck, die waehrend der Umstellung noch in der Datenbank steht.
        """
        if not sensor_id:
            return None

        if sensor_id.startswith("hwmon:"):
            sensor_id = sensor_id[len("hwmon:"):]

        temp_path = self._temp_paths.get(sensor_id)
        if temp_path is None:
            temp_path = self._legacy_temp_path(sensor_id)
        if temp_path is None:
            return None

        temp_value = await self._read_hwmon_file(temp_path)
        if temp_value is not None:
            return float(temp_value) / 1000.0
        return None

    def _legacy_temp_path(self, sensor_id: str) -> Optional[Path]:
        """Altform "hwmon0_temp1" -> Pfad. Nur fuer noch nicht migrierte IDs."""
        parts = sensor_id.split("_")
        if len(parts) != 2:
            return None
        hwmon_name, temp_name = parts
        if not hwmon_name.startswith("hwmon") or not temp_name.startswith("temp"):
            return None
        if "/" in hwmon_name or "\\" in hwmon_name or ".." in hwmon_name:
            return None
        if not temp_name[len("temp"):].isdigit():
            return None
        return self._hwmon_base / hwmon_name / f"{temp_name}_input"

    def _find_cpu_temp_sensor(self) -> Optional[Tuple[str, Path]]:
        """Find CPU temperature sensor across all hwmon directories.

        Searches for known CPU temperature drivers (k10temp, coretemp, etc.)
        in any hwmon directory, not just the one containing the PWM fan.

        Returns:
            Tuple of (sensor_id, temp_path) or None if not found
        """
        if not self._hwmon_base.exists():
            return None

        identities = derive_all(self._hwmon_base)

        for hwmon_dir in sorted(self._hwmon_base.iterdir(), key=_by_leading_number):
            if not hwmon_dir.is_dir() or not hwmon_dir.name.startswith("hwmon"):
                continue

            name_file = hwmon_dir / "name"
            if not name_file.exists():
                continue

            try:
                driver_name = name_file.read_text().strip()
            except Exception:
                continue

            if driver_name not in self._CPU_SENSOR_DRIVERS:
                continue

            identity = identities.get(hwmon_dir.name)
            if identity is None:
                continue

            # Found a CPU sensor driver -- use its lowest-numbered temp input
            for temp_file in sorted(hwmon_dir.glob("temp[0-9]*_input"),
                                    key=_by_leading_number):
                temp_num = temp_file.name.replace("temp", "").replace("_input", "")
                sensor_id = build_sensor_id(identity, int(temp_num))
                # I-3: ohne diesen Eintrag bliebe get_temperature() fuer einen
                # Chip, der erst NACH dem Startscan erscheint (Treiber
                # nachgeladen), dauerhaft None -- _temp_paths wird sonst
                # ausschliesslich in _scan_pwm_fans gefuellt, das nur beim
                # Start und in switch_backend laeuft.
                self._temp_paths.setdefault(sensor_id, temp_file)
                logger.info(
                    f"Found CPU temp sensor: {sensor_id} (driver={driver_name})"
                )
                return sensor_id, temp_file

        return None

    async def get_available_temp_sensors(self) -> List[TempSensorData]:
        """List all available temperature sensors across all hwmon directories."""
        sensors: List[TempSensorData] = []

        if not self._hwmon_base.exists():
            return sensors

        identities = derive_all(self._hwmon_base)

        for hwmon_dir in sorted(self._hwmon_base.iterdir(), key=_by_leading_number):
            if not hwmon_dir.is_dir() or not hwmon_dir.name.startswith("hwmon"):
                continue

            identity = identities.get(hwmon_dir.name)
            if identity is None:
                continue

            name_file = hwmon_dir / "name"
            device_name = "Unknown"
            if name_file.exists():
                try:
                    device_name = name_file.read_text().strip()
                except Exception:
                    pass

            is_cpu = device_name in self._CPU_SENSOR_DRIVERS

            for temp_file in sorted(hwmon_dir.glob("temp[0-9]*_input"),
                                    key=_by_leading_number):
                temp_num = temp_file.name.replace("temp", "").replace("_input", "")
                sensor_id = build_sensor_id(identity, int(temp_num))
                # I-3: gleicher Grund wie in _find_cpu_temp_sensor -- ohne
                # diesen Eintrag ist ein erst nachtraeglich gelisteter Sensor
                # zwar in der Auswahlliste sichtbar, aber get_temperature()
                # findet ihn nie (kein Scan-Lauf hat ihn eingetragen).
                self._temp_paths.setdefault(sensor_id, temp_file)

                # Try to read label
                label = None
                label_file = hwmon_dir / f"temp{temp_num}_label"
                if label_file.exists():
                    try:
                        label = label_file.read_text().strip()
                    except Exception:
                        pass

                # Read current temperature
                current_temp = None
                temp_value = await self._read_hwmon_file(temp_file)
                if temp_value is not None:
                    current_temp = float(temp_value) / 1000.0

                sensors.append(TempSensorData(
                    sensor_id=sensor_id,
                    device_name=device_name,
                    label=label,
                    is_cpu_sensor=is_cpu,
                    current_temp=current_temp,
                ))

        return sensors

    async def _scan_pwm_fans(self) -> Dict[str, Dict]:
        """Scan hwmon for PWM fans.

        Builds a new dict from sysfs. Only replaces the cache if the scan
        found at least one fan (or the cache was empty), preventing
        transient sysfs I/O failures from clearing known fans.

        Prefers CPU temperature sensor (k10temp, coretemp) over local
        board sensors for fan control.
        """
        new_cache: Dict[str, Dict] = {}
        new_temp_paths: Dict[str, Path] = {}
        identities = derive_all(self._hwmon_base)

        if not self._hwmon_base.exists():
            if not self._fan_cache:
                return {}
            logger.debug("hwmon base missing but cache exists, keeping cached fans")
            return self._fan_cache

        # Find CPU temp sensor across all hwmon directories
        cpu_sensor = self._find_cpu_temp_sensor()
        cpu_sensor_id = cpu_sensor[0] if cpu_sensor else None
        cpu_temp_path = cpu_sensor[1] if cpu_sensor else None

        for hwmon_dir in sorted(self._hwmon_base.iterdir(), key=_by_leading_number):
            if not hwmon_dir.is_dir() or not hwmon_dir.name.startswith("hwmon"):
                continue

            identity = identities.get(hwmon_dir.name)
            if identity is None:
                continue

            # Rueckabbildung auf Ebene der hwmon-Schleife eintragen, nicht
            # erst innerhalb der PWM-Schleife (R1, #532): Chips ohne Luefter
            # (k10temp, NVMe) liefern Kurvenquellen fuer get_temperature()
            # und muessten sonst aufloesbar bleiben, obwohl sie hier nie
            # einen PWM-Kanal durchlaufen.
            for temp_file in sorted(hwmon_dir.glob("temp[0-9]*_input"),
                                    key=_by_leading_number):
                num = temp_file.name[len("temp"):-len("_input")]
                new_temp_paths[build_sensor_id(identity, int(num))] = temp_file

            # Read hwmon name
            name_file = hwmon_dir / "name"
            hwmon_name_value = "Unknown"
            if name_file.exists():
                try:
                    hwmon_name_value = name_file.read_text().strip()
                except Exception:
                    pass

            # GPU recognition
            is_gpu_fan = hwmon_name_value in {"amdgpu", "nouveau"}
            gpu_vendor = (
                "amd" if hwmon_name_value == "amdgpu"
                else ("nvidia" if hwmon_name_value == "nouveau" else None)
            )

            # Find PWM files
            for pwm_file in sorted(hwmon_dir.glob("pwm[0-9]*"), key=_by_leading_number):
                if "_" in pwm_file.name:  # Skip pwm1_enable, etc
                    continue

                pwm_num = pwm_file.name.replace("pwm", "")
                fan_id = build_fan_id(identity, int(pwm_num))

                # Find corresponding fan input
                fan_input_path = hwmon_dir / f"fan{pwm_num}_input"
                if not fan_input_path.exists():
                    continue

                # Find PWM enable
                pwm_enable_path = hwmon_dir / f"pwm{pwm_num}_enable"

                # pwm_enable EINMAL pro Start lesen, bevor set_pwm es auf 1
                # setzt. Nach dem ersten Regelzyklus steht dort unser eigener
                # Wert -- dies ist der einzige Moment, in dem der Board-Wert
                # sichtbar sein kann (#534).
                pwm_enable_at_scan = None
                if pwm_enable_path.exists():
                    pwm_enable_at_scan = await self._read_hwmon_file(pwm_enable_path)

                # Prefer CPU sensor over local board sensor
                if cpu_sensor_id:
                    temp_sensor_id = cpu_sensor_id
                    temp_path = cpu_temp_path
                else:
                    # Fallback: lowest-numbered temp sensor in same hwmon dir
                    temp_sensor_id = None
                    temp_path = None
                    for temp_file in sorted(hwmon_dir.glob("temp[0-9]*_input"),
                                            key=_by_leading_number):
                        temp_num = temp_file.name.replace("temp", "").replace("_input", "")
                        temp_sensor_id = build_sensor_id(identity, int(temp_num))
                        temp_path = temp_file
                        break

                pwm_control = PwmControl.SUPPORTED
                if gpu_vendor == "amd":
                    try:
                        pwm_control = probe_amd_pwm_control(hwmon_dir)
                    except OSError as exc:
                        logger.debug(f"pwm_control probe failed for {hwmon_dir}: {exc}")

                new_cache[fan_id] = {
                    "name": f"{hwmon_name_value} PWM{pwm_num}",
                    "pwm_path": pwm_file,
                    "pwm_enable_path": pwm_enable_path if pwm_enable_path.exists() else None,
                    "pwm_enable_at_scan": pwm_enable_at_scan,
                    "fan_input_path": fan_input_path,
                    "temp_path": temp_path,
                    "temp_sensor_id": temp_sensor_id,
                    "is_gpu_fan": is_gpu_fan,
                    "gpu_vendor": gpu_vendor,
                    "device_driver": hwmon_name_value,
                    "pwm_control": pwm_control,
                    "identity_stable": identity.stable,
                }

        if new_cache or not self._fan_cache:
            self._fan_cache = new_cache
            self._temp_paths = new_temp_paths
            # Backoff-Eintraege verschwundener Luefter mitnehmen, sonst waechst
            # das Dict ueber Treiber-Reloads und hwmon-Renumbering hinweg (#533).
            for stale in set(self._write_backoff) - set(self._fan_cache):
                del self._write_backoff[stale]
            logger.info(f"Scanned hwmon: found {len(self._fan_cache)} PWM fan(s)")
        else:
            logger.warning(
                f"hwmon scan found 0 fans but cache has {len(self._fan_cache)}, keeping cached fans"
            )

        return self._fan_cache

    async def _read_hwmon_file(self, path: Path) -> Optional[int]:
        """Read integer value from hwmon sysfs file."""
        if not path or not path.exists():
            return None

        try:
            value = path.read_text().strip()
            return int(value)
        except Exception as e:
            logger.debug(f"Failed to read {path}: {e}")
            return None

    async def _write_hwmon_file(self, path: Path, value: str) -> Tuple[bool, Optional[int]]:
        """Write value to hwmon sysfs file.

        Returns (ok, errno). errno ist der Code des letzten fehlgeschlagenen
        Versuchs, damit der Aufrufer EACCES (fehlende Rechte) von EINVAL
        (Treiber lehnt ab) unterscheiden kann — beide brauchen voellig
        verschiedene Handlungsempfehlungen.
        """
        if not path or not path.exists():
            return False, None

        try:
            path.write_text(value + "\n")
            self._has_write_permission = True
            return True, None
        except OSError as exc:
            code = exc.errno
            if code not in (errno.EACCES, errno.EPERM):
                logger.debug(f"Write to {path} failed: {exc}")
                return False, code

            # Fehlende Rechte: sudo-tee-Fallback. -n, damit ein fehlender
            # sudoers-Eintrag sofort scheitert statt in den Timeout zu laufen.
            try:
                result = subprocess.run(
                    ["sudo", "-n", "tee", str(path)],
                    input=value.encode(),
                    capture_output=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    self._has_write_permission = True
                    logger.debug(f"Wrote to {path} via sudo tee")
                    return True, None
                # DEBUG statt WARNING (#533): der Aufrufer meldet die Episode
                # bereits mit einer ERROR-Zeile; hier wuerde sie pro Zyklus
                # ein zweites Mal auflaufen.
                logger.debug(f"sudo tee failed for {path}: {result.stderr.decode()}")
            except Exception as exc2:
                logger.error(f"Failed to write {path} with sudo: {exc2}")
            return False, code
        except Exception as exc:
            # Catch-all wie bisher: nichts Unerwartetes in den Loop propagieren.
            logger.error(f"Failed to write {path}: {exc}")
            return False, None

    def _pwm_to_percent(self, pwm_value: int) -> int:
        """Convert PWM value (0-255) to percentage (0-100)."""
        return round(pwm_value * 100 / 255)

    def _percent_to_pwm(self, percent: int) -> int:
        """Convert percentage (0-100) to PWM value (0-255)."""
        return round(percent * 255 / 100)

    def _get_default_curve(self) -> List[FanCurvePoint]:
        """Get default temperature-PWM curve."""
        return [
            FanCurvePoint(temp=35, pwm=30),
            FanCurvePoint(temp=50, pwm=50),
            FanCurvePoint(temp=70, pwm=80),
            FanCurvePoint(temp=85, pwm=100),
        ]
