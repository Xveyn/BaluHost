"""Geplanter Systemneustart: Gates, Zustandsautomat, Ausführung.

Angestoßen vom 60-Sekunden-Tick in `SleepManagerService._schedule_check_loop()`.
Warum hier und nicht im Scheduler-Worker: Kernbetriebszeit, Display-Erkennung,
`enter_true_suspend()` und die `wake_at`-Klemmung liegen alle im Power-Layer,
und der Worker ist ein eigener Prozess ohne `SleepManagerService`.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.scheduler_history import SchedulerExecution, SchedulerStatus
from app.services.power import core_uptime as core_uptime_helpers
from app.services.power.gpu.display_detector import get_active_display_count_sync

logger = logging.getLogger(__name__)

SKIP_CORE_UPTIME = "core_uptime"
SKIP_DISPLAYS = "displays_on"
SKIP_SCHEDULER_JOB = "scheduler_job_running"
SKIP_NOT_IDLE = "system_busy"
SKIP_REBOOT_FAILED = "reboot_command_failed"
SKIP_STALE = "reboot_outcome_unknown"

SKIP_REASON_LABELS: dict[str, str] = {
    SKIP_CORE_UPTIME: "Kernbetriebszeit aktiv",
    SKIP_DISPLAYS: "Displays aktiv",
    SKIP_SCHEDULER_JOB: "ein Wartungsjob läuft",
    SKIP_NOT_IDLE: "das System ist ausgelastet",
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
    sleep_service,
    own_execution_id: Optional[int],
) -> Optional[str]:
    """Der erste Grund, der den Neustart verhindert — oder `None`.

    Die Reihenfolge ist Teil des Vertrags: sie bestimmt, welcher Grund in der
    Skip-Meldung landet, und sortiert vom „grundsätzlich verboten" zum
    „gerade ungünstig".
    """
    # 1) Kernbetriebszeit — Verfügbarkeitszusage. Ein Neustart kappt SMB,
    #    Sync und Uploads auch dann, wenn kein Monitor an ist.
    try:
        master, windows = sleep_service._load_core_uptime()
        if master:
            in_core, _ = core_uptime_helpers.is_in_core_uptime(datetime.now(), windows)
            if in_core:
                return SKIP_CORE_UPTIME
    except Exception as exc:
        # Fail-closed: wer die Kernbetriebszeit nicht lesen kann, startet nicht neu.
        logger.warning("Kernbetriebszeit nicht lesbar — Neustart verschoben: %s", exc)
        return SKIP_CORE_UPTIME

    # 2) Display an — jemand sitzt an der Box.
    if displays_block():
        return SKIP_DISPLAYS

    # 3) Laufender Wartungsjob — ein halbes Backup ist schlimmer als ein
    #    verschobener Neustart.
    try:
        if _another_scheduler_job_running(db, own_execution_id):
            return SKIP_SCHEDULER_JOB
    except Exception as exc:
        logger.warning("Scheduler-Zustand nicht lesbar — Neustart verschoben: %s", exc)
        return SKIP_SCHEDULER_JOB

    # 4) System nicht idle — deckt CPU, Disk-I/O (und damit SMB), Uploads und
    #    HTTP-Rate mit denselben Schwellen ab, die über den Auto-Suspend
    #    entscheiden.
    try:
        config = sleep_service._load_config()
        if config is not None and not sleep_service._is_system_idle(
            config, sleep_service._get_activity_metrics()
        ):
            return SKIP_NOT_IDLE
    except Exception as exc:
        logger.warning("Idle-Zustand nicht lesbar — Neustart verschoben: %s", exc)
        return SKIP_NOT_IDLE

    return None
