"""Geplanter Systemneustart: Gates, Zustandsautomat, Ausführung.

Angestoßen vom 60-Sekunden-Tick in `SleepManagerService._schedule_check_loop()`.
Warum hier und nicht im Scheduler-Worker: Kernbetriebszeit, Display-Erkennung,
`enter_true_suspend()` und die `wake_at`-Klemmung liegen alle im Power-Layer,
und der Worker ist ein eigener Prozess ohne `SleepManagerService`.
"""
from __future__ import annotations

import logging
import subprocess
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.scheduler_history import SchedulerExecution, SchedulerStatus
from app.services.power import core_uptime as core_uptime_helpers
from app.services.power.gpu.display_detector import get_active_display_count_sync

if TYPE_CHECKING:
    # Nur für den Type Checker — vermeidet einen Zirkelimport mit sleep.py.
    from app.services.power.sleep import SleepManagerService

logger = logging.getLogger(__name__)

SKIP_CORE_UPTIME = "core_uptime"
SKIP_DISPLAYS = "displays_on"
SKIP_SCHEDULER_JOB = "scheduler_job_running"
SKIP_NOT_IDLE = "system_busy"
SKIP_UNREADABLE = "state_unreadable"
SKIP_REBOOT_FAILED = "reboot_command_failed"
SKIP_STALE = "reboot_outcome_unknown"

SKIP_REASON_LABELS: dict[str, str] = {
    SKIP_CORE_UPTIME: "Kernbetriebszeit aktiv",
    SKIP_DISPLAYS: "Displays aktiv",
    SKIP_SCHEDULER_JOB: "ein Wartungsjob läuft",
    SKIP_NOT_IDLE: "das System ist ausgelastet",
    SKIP_UNREADABLE: "der Systemzustand ist nicht lesbar",
    SKIP_REBOOT_FAILED: "der Neustart-Befehl schlug fehl",
    SKIP_STALE: "der Ausgang des Neustarts ist unbekannt",
}


def displays_block() -> bool:
    """Ob ein eingeschaltetes Display den Neustart verhindert.

    Bewusst NICHT `gaming_presence.displays_on()`: die liefert im Dev-Mode
    hart `True`. Für das Gaming-Gate ist das die harmlose Richtung (es lässt
    einen Suspend durch), hier wäre es die fatale — das Feature wäre lokal nie
    auslösbar.

    Unlesbare Angaben zählen hier als „Display an" und blockieren. Auch das ist
    die Gegenrichtung zum Gaming-Gate: ein Neustart ist die eingreifendere
    Aktion, bei Unwissen wird er verschoben statt durchgezogen.
    """
    if settings.is_dev_mode:
        return False
    try:
        return get_active_display_count_sync() > 0
    except Exception as exc:
        logger.warning("Display-Zustand unlesbar — Neustart wird verschoben: %s", exc)
        return True


def _another_scheduler_job_running(db: Session, own_execution_id: Optional[int]) -> bool:
    query = db.query(SchedulerExecution).filter(
        SchedulerExecution.status == SchedulerStatus.RUNNING.value
    )
    if own_execution_id is not None:
        query = query.filter(SchedulerExecution.id != own_execution_id)
    return query.first() is not None


def gates_blocking(
    db: Session,
    sleep_service: "SleepManagerService",
    own_execution_id: Optional[int],
) -> Optional[str]:
    """Der erste Grund, der den Neustart verhindert — oder `None`.

    Die Reihenfolge ist Teil des Vertrags: sie bestimmt, welcher Grund in der
    Skip-Meldung landet, und sortiert vom „grundsätzlich verboten" zum
    „gerade ungünstig".
    """
    # 0) Erreichbarkeitsprüfung. `SleepManagerService._load_config()` und
    #    `_load_core_uptime()` schlucken DB-Fehler bereits selbst und liefern
    #    im Fehlerfall harmlose Defaults (`None` bzw. `(False, [])`) statt zu
    #    werfen — die try/except-Blöcke in den einzelnen Gates unten fangen
    #    einen DB-Ausfall also NICHT ab. Diese triviale eigene Abfrage ist
    #    deshalb die einzige Stelle, an der "fail-closed" tatsächlich
    #    erzwungen wird: schlägt sie fehl, ist der Systemzustand unbekannt und
    #    der Neustart wird verschoben, bevor irgendein Gate läuft.
    try:
        db.query(SchedulerExecution.id).limit(1).first()
    except Exception as exc:
        logger.warning("Systemzustand nicht lesbar — Neustart verschoben: %s", exc)
        return SKIP_UNREADABLE

    # 1) Kernbetriebszeit — Verfügbarkeitszusage. Ein Neustart kappt SMB,
    #    Sync und Uploads auch dann, wenn kein Monitor an ist.
    #    `_load_core_uptime()` wirft laut eigenem Vertrag nie (siehe oben) —
    #    dieses except fängt daher nur `core_uptime_helpers.is_in_core_uptime()`
    #    ab, z. B. bei defekten Fenster-Daten. Der Schutz gegen einen
    #    DB-Ausfall ist bereits die Erreichbarkeitsprüfung in Schritt 0.
    try:
        master, windows = sleep_service._load_core_uptime()
        if master:
            in_core, _ = core_uptime_helpers.is_in_core_uptime(datetime.now(), windows)
            if in_core:
                return SKIP_CORE_UPTIME
    except Exception as exc:
        logger.warning("Kernbetriebszeit nicht lesbar — Neustart verschoben: %s", exc)
        return SKIP_CORE_UPTIME

    # 2) Display an — jemand sitzt an der Box.
    if displays_block():
        return SKIP_DISPLAYS

    # 3) Laufender Wartungsjob — ein halbes Backup ist schlimmer als ein
    #    verschobener Neustart. Ein DB-Ausfall an dieser Stelle ist durch
    #    Schritt 0 bereits abgedeckt; dieses except bleibt als Netz für
    #    andere, unerwartete Fehler.
    try:
        if _another_scheduler_job_running(db, own_execution_id):
            return SKIP_SCHEDULER_JOB
    except Exception as exc:
        logger.warning("Scheduler-Zustand nicht lesbar — Neustart verschoben: %s", exc)
        return SKIP_SCHEDULER_JOB

    # 4) System nicht idle — deckt CPU, Disk-I/O (und damit SMB), Uploads und
    #    HTTP-Rate mit denselben Schwellen ab, die über den Auto-Suspend
    #    entscheiden. `_load_config()` wirft laut eigenem Vertrag nie.
    config = sleep_service._load_config()
    if config is None:
        # Kein Fehlerfall: die `sleep_config`-Zeile wird ausschließlich von
        # `SleepManagerService.update_config()` angelegt (sleep.py:1488).
        # Auf einer Box, auf der nie jemand die Schlafeinstellungen
        # gespeichert hat, ist `config is None` der Normalfall — ohne
        # gespeicherte Schwellen gibt es keine Definition von "idle", also
        # wird Gate 4 übersprungen statt fälschlich zu blockieren oder
        # durchzulassen. Ein echter DB-Ausfall ist bereits durch die
        # Erreichbarkeitsprüfung in Schritt 0 abgefangen.
        logger.info("Keine Sleep-Config vorhanden — Gate 4 (Idle-Check) übersprungen")
    else:
        try:
            if not sleep_service._is_system_idle(
                config, sleep_service._get_activity_metrics()
            ):
                return SKIP_NOT_IDLE
        except Exception as exc:
            logger.warning("Idle-Zustand nicht lesbar — Neustart verschoben: %s", exc)
            return SKIP_NOT_IDLE

    return None


_REBOOT_CMD = ["sudo", "systemctl", "reboot"]


def run_reboot_command() -> tuple[bool, str]:
    """Startet das System neu. Rückgabe `(ok, detail)`.

    Im Dev-Mode passiert nichts — der Aufrufer simuliert den Boot-Übergang
    (siehe `tick`), damit der Automat lokal durchlaufbar bleibt.

    Der sudoers-Eintrag dafür steht in
    `deploy/install/templates/sudoers-baluhost-power` und erreicht eine
    bestehende Box NUR über einen `SYNC_PERMISSIONS=1`-Deploy. Fehlt er,
    scheitert der Aufruf sauber und der Automat meldet den Grund.
    """
    if settings.is_dev_mode:
        logger.warning("DEV-MODE: `sudo systemctl reboot` wird NICHT ausgeführt")
        return True, "dev-mode: simulierter Neustart"

    try:
        result = subprocess.run(
            _REBOOT_CMD, capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return False, "timeout nach 30s"
    except Exception as exc:  # pragma: no cover - defensiv
        return False, str(exc)

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        return False, detail or f"rc={result.returncode}"
    return True, "ok"
