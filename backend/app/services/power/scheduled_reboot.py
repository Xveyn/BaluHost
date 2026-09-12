"""Geplanter Systemneustart: Gates, Zustandsautomat, Ausführung.

Angestoßen vom 60-Sekunden-Tick in `SleepManagerService._schedule_check_loop()`.
Warum hier und nicht im Scheduler-Worker: Kernbetriebszeit, Display-Erkennung,
`enter_true_suspend()` und die `wake_at`-Klemmung liegen alle im Power-Layer,
und der Worker ist ein eigener Prozess ohne `SleepManagerService`.
"""
from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.scheduler_history import SchedulerExecution, SchedulerStatus
from app.services.audit.logger_db import get_audit_logger_db
from app.services.notifications.events import (
    emit_reboot_scheduled_sync,
    emit_reboot_skipped_sync,
    emit_reboot_started_sync,
)
from app.services.power import core_uptime as core_uptime_helpers
from app.services.power.gpu.display_detector import get_active_display_count_sync
from app.services.power.reboot_schedule import due_occurrence, next_weekday_occurrence
from app.services.power.reboot_state import (
    PHASE_ARMED,
    PHASE_EXECUTING,
    PHASE_IDLE,
    PHASE_RESUSPEND_PENDING,
    close_execution,
    get_state,
    load_enabled_config,
    open_execution,
    reset_to_idle,
    same_instant,
    to_local,
    to_utc,
)

if TYPE_CHECKING:
    # Nur für den Type Checker — vermeidet einen Zirkelimport mit sleep.py.
    # `from __future__ import annotations` oben macht alle Annotationen zu
    # Strings, deshalb braucht keiner dieser Namen einen Laufzeitimport.
    from app.models.scheduled_reboot import ScheduledRebootState
    from app.schemas.scheduler import RebootScheduleConfig
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


# ---------------------------------------------------------------------------
# Zustandsautomat
# ---------------------------------------------------------------------------

# Ein `executing`, das länger als das hier zurückliegt, gilt als gescheitert.
# Großzügig gegenüber einem normalen Boot (unter zwei Minuten), eng genug,
# dass die Fehlmeldung nicht Tage später kommt.
STALE_EXECUTING_AFTER = timedelta(minutes=30)

# Kommt der Wieder-Suspend in dieser Zeit nicht zustande, übernimmt die
# normale Auto-Idle-Mechanik.
RESUSPEND_TIMEOUT = timedelta(minutes=30)

_WEEKDAY_NAMES_DE = [
    "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag",
]


def _now_local() -> datetime:
    """Server-lokale naive Zeit. Eigene Funktion, damit Tests sie ersetzen können."""
    return datetime.now()


def _human_due(due_local: datetime) -> str:
    """Der Termin als deutsche Klartextangabe für die Vorwarnung."""
    return f"{_WEEKDAY_NAMES_DE[due_local.weekday()]}, {due_local:%H:%M}"


def _audit_reboot(due_local: datetime, execution_id: Optional[int]) -> None:
    """Schreibt den Audit-Eintrag unmittelbar vor der Ausführung."""
    try:
        get_audit_logger_db().log_event(
            event_type="system",
            user=None,
            action="scheduled_reboot",
            resource="system_reboot",
            details={
                "due_at": due_local.isoformat(),
                "execution_id": execution_id,
                "gates": "open",
            },
            success=True,
        )
    except Exception as exc:  # pragma: no cover - Audit darf nie blockieren
        logger.warning("Audit-Eintrag für den Neustart fehlgeschlagen: %s", exc)


def _safe_rollback(db: Session) -> None:
    """Rollback, der selbst nie wirft.

    Ein geplatzter `commit()` lässt die Transaktion vergiftet zurück; jeder
    weitere Zugriff auf dieselbe Session scheitert dann mit
    `PendingRollbackError`. Der Sleep-Loop öffnet zwar pro Tick eine frische
    Session, aber diese Funktionen dürfen sich darauf nicht verlassen.
    """
    try:
        db.rollback()
    except Exception as exc:  # pragma: no cover - defensiv
        logger.warning("Rollback nach einem Fehler fehlgeschlagen: %s", exc)


def tick(db: Session, sleep_service: "SleepManagerService", awake: bool) -> None:
    """Ein Schritt des Automaten. Wird alle 60 Sekunden aufgerufen.

    `awake` sagt, ob die Box gerade wach ist — davon hängt nur die Vorwarnung ab.
    Wirft nie; der Aufrufer ist der Sleep-Loop und darf nicht abreißen.
    """
    try:
        state = get_state(db)
        if state.phase == PHASE_RESUSPEND_PENDING:
            _tick_resuspend(db, state)
            return
        if state.phase == PHASE_EXECUTING:
            # Der Neustart läuft; nach dem Boot übernimmt `on_boot`.
            return

        config = load_enabled_config(db)
        if config is None:
            if state.phase != PHASE_IDLE:
                # Die offene Execution MUSS mit weg. Bliebe sie auf `running`,
                # zählte sie in Gate 3 als fremder Wartungsjob (dort wird nur
                # die *eigene* ID ausgeschlossen) und blockierte jeden künftigen
                # Neustart, bis ein Prozessneustart sie aufräumt.
                close_execution(
                    db, state.execution_id, SchedulerStatus.CANCELLED.value,
                    error="Zeitplan wurde deaktiviert",
                )
                reset_to_idle(db, state)
            return

        now = _now_local()
        if state.phase == PHASE_ARMED:
            _tick_armed(db, state, config, sleep_service, now)
            return

        _tick_idle(db, state, config, sleep_service, now, awake)
    except Exception as exc:
        logger.warning("Neustart-Tick fehlgeschlagen (Zustand unverändert): %s", exc)
        _safe_rollback(db)


def _tick_idle(
    db: Session,
    state: "ScheduledRebootState",
    config: RebootScheduleConfig,
    sleep_service: "SleepManagerService",
    now: datetime,
    awake: bool,
) -> None:
    """Vorwarnung senden und bei Fälligkeit armen."""
    retry = timedelta(hours=config.retry_window_hours)

    # Vorwarnung — nur wach, nur einmal pro Termin.
    if awake and config.warning_lead_minutes > 0:
        upcoming = next_weekday_occurrence(now, config.weekday, config.time)
        lead = timedelta(minutes=config.warning_lead_minutes)
        # UTC-seitig vergleichen, siehe `same_instant` — in Ortszeit wäre der
        # Vergleich am Umstellungssonntag falsch und die Vorwarnung ginge in
        # derselben Minute erneut raus.
        already = same_instant(state.warned_for_due_at, to_utc(upcoming))
        if not already and upcoming - now <= lead:
            emit_reboot_scheduled_sync(_human_due(upcoming))
            state.warned_for_due_at = to_utc(upcoming)
            db.commit()

    due = due_occurrence(now, config.weekday, config.time, retry)
    if due is None:
        return

    # Wiederholungssperre. `due_occurrence` kann „Zustand ging verloren" und
    # „Termin ist erledigt" nicht unterscheiden; ohne diese Prüfung startet
    # die Box nach dem Neustart in einer Schleife erneut neu.
    #
    # Der Vergleich läuft UTC-seitig (`same_instant`), nicht über `to_local`:
    # bei einer `time` zwischen 02:00 und 02:59 gibt es die Ortszeit am
    # Umstellungssonntag im Frühjahr nicht, `to_local(to_utc(x)) != x`, und
    # die Sperre würde genau dort ausfallen, wo sie gebraucht wird.
    if same_instant(state.last_completed_due_at, to_utc(due)):
        return

    state.phase = PHASE_ARMED
    state.due_at = to_utc(due)
    state.deadline_at = to_utc(due + retry)
    state.execution_id = open_execution(db)
    state.last_skip_reason = None
    state.phase_entered_at = datetime.now(timezone.utc)
    db.commit()
    logger.info("Geplanter Neustart gearmt für %s (Frist bis %s)", due, due + retry)

    _tick_armed(db, state, config, sleep_service, now)


def _tick_armed(
    db: Session,
    state: "ScheduledRebootState",
    config: RebootScheduleConfig,
    sleep_service: "SleepManagerService",
    now: datetime,
) -> None:
    """Frist prüfen, Gates prüfen, ausführen."""
    if state.due_at is None:
        # `armed` ohne Termin ist ein korrupter Zustand — nur so entstanden,
        # dass jemand die Zeile von Hand angefasst hat. Weiterlaufen wäre
        # gefährlich: die Frist ließe sich nicht prüfen, und ein Abschluss über
        # `to_utc(now)` würde die Wiederholungssperre auf den falschen Moment
        # setzen. Also aufräumen und die bestehende Sperre NICHT anfassen
        # (`reset_to_idle` ohne `completed_due_at` lässt sie stehen).
        logger.warning(
            "Neustart-Zustand korrupt (Phase %s ohne due_at) — zurückgesetzt",
            state.phase,
        )
        close_execution(
            db, state.execution_id, SchedulerStatus.CANCELLED.value,
            error=SKIP_REASON_LABELS[SKIP_STALE],
        )
        reset_to_idle(db, state)
        return

    due_local = to_local(state.due_at)

    if state.deadline_at is not None and now > to_local(state.deadline_at):
        reason = state.last_skip_reason or SKIP_NOT_IDLE
        close_execution(
            db, state.execution_id, SchedulerStatus.CANCELLED.value,
            error=SKIP_REASON_LABELS.get(reason, reason),
        )
        emit_reboot_skipped_sync(SKIP_REASON_LABELS.get(reason, reason))
        reset_to_idle(db, state, completed_due_at=to_utc(due_local))
        logger.info("Geplanter Neustart verfallen (%s)", reason)
        return

    blocking = gates_blocking(db, sleep_service, state.execution_id)
    if blocking is not None:
        if state.last_skip_reason != blocking:
            state.last_skip_reason = blocking
            db.commit()
        logger.info("Geplanter Neustart wartet: %s", SKIP_REASON_LABELS.get(blocking))
        return

    _execute(db, state, due_local)


def _execute(db: Session, state: "ScheduledRebootState", due_local: datetime) -> None:
    """Audit, Meldung, Phasenwechsel, Neustart-Befehl — in dieser Reihenfolge."""
    _audit_reboot(due_local, state.execution_id)

    try:
        emit_reboot_started_sync()
    except Exception as exc:
        logger.warning("Startmeldung fehlgeschlagen — Neustart läuft trotzdem: %s", exc)

    # Diese Zeile MUSS vor dem Befehl committet sein. Nach dem Neustart ist sie
    # der einzige Beweis, dass es ein geplanter war.
    state.phase = PHASE_EXECUTING
    state.phase_entered_at = datetime.now(timezone.utc)
    db.commit()

    ok, detail = run_reboot_command()
    if not ok:
        logger.error("Geplanter Neustart fehlgeschlagen: %s", detail)
        close_execution(
            db, state.execution_id, SchedulerStatus.FAILED.value, error=detail,
        )
        emit_reboot_skipped_sync(
            f"{SKIP_REASON_LABELS[SKIP_REBOOT_FAILED]} ({detail})"
        )
        reset_to_idle(db, state, completed_due_at=to_utc(due_local))
        return

    if settings.is_dev_mode:
        # Kein echter Neustart — den Boot-Übergang direkt simulieren, sonst
        # bliebe der Automat lokal für immer auf `executing` stehen.
        logger.info("DEV-MODE: simuliere den Boot-Übergang")
        on_boot(db)


def _tick_resuspend(db: Session, state: "ScheduledRebootState") -> None:
    """Timeout-Wache. Der eigentliche Suspend passiert im Sleep-Loop (Task 8)."""
    entered = state.phase_entered_at
    if entered is None:
        reset_to_idle(db, state)
        return
    if entered.tzinfo is None:
        entered = entered.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - entered > RESUSPEND_TIMEOUT:
        logger.info(
            "Wieder-Suspend nach dem Neustart kam nicht zustande — "
            "die normale Auto-Idle-Mechanik übernimmt"
        )
        reset_to_idle(db, state)


def on_boot(db: Session) -> Optional[str]:
    """Wertet die Phase nach einem Boot aus. Von `lifespan` aufgerufen.

    Rückgabe:
      "completed" — geplanter Neustart erfolgreich; Folgephase gesetzt
      "stale"     — `executing` zu alt oder korrupt, als gescheitert gewertet
      None        — kein geplanter Neustart im Spiel
    """
    try:
        state = get_state(db)
        if state.phase != PHASE_EXECUTING:
            return None

        due_utc = state.due_at
        if due_utc is None:
            # Korrupter Zustand. Ohne diesen Zweig schriebe der
            # `woke_for_reboot`-Pfad unten `last_completed_due_at = None` und
            # löschte damit eine bestehende Sperre — aus einem kaputten
            # Zustand würde eine Neustart-Schleife. Wie beim echten `stale`:
            # kein Wieder-Suspend, Ausgang unbekannt. Die vorhandene Sperre
            # bleibt unangetastet (`reset_to_idle` ohne `completed_due_at`).
            logger.warning(
                "Neustart-Zustand korrupt (executing ohne due_at) — "
                "als gescheitert gewertet, Wiederholungssperre unverändert"
            )
            close_execution(
                db, state.execution_id, SchedulerStatus.FAILED.value,
                error=SKIP_REASON_LABELS[SKIP_STALE],
            )
            reset_to_idle(db, state)
            return "stale"

        entered = state.phase_entered_at
        if entered is not None and entered.tzinfo is None:
            entered = entered.replace(tzinfo=timezone.utc)

        stale = (
            entered is None
            or datetime.now(timezone.utc) - entered > STALE_EXECUTING_AFTER
        )

        if stale:
            close_execution(
                db, state.execution_id, SchedulerStatus.FAILED.value,
                error=SKIP_REASON_LABELS[SKIP_STALE],
            )
            # Kein Wieder-Suspend: bei unklarem Ausgang darf die Box nicht
            # wieder schlafen gehen, sonst kommt niemand mehr dran.
            reset_to_idle(db, state, completed_due_at=due_utc)
            return "stale"

        close_execution(
            db, state.execution_id, SchedulerStatus.COMPLETED.value,
            result='{"rebooted": true}',
        )

        if state.woke_for_reboot:
            state.phase = PHASE_RESUSPEND_PENDING
            state.execution_id = None
            state.due_at = None
            state.deadline_at = None
            state.last_completed_due_at = due_utc
            state.phase_entered_at = datetime.now(timezone.utc)
            db.commit()
        else:
            reset_to_idle(db, state, completed_due_at=due_utc)
        return "completed"
    except Exception as exc:
        logger.warning("Boot-Auswertung des Neustarts fehlgeschlagen: %s", exc)
        _safe_rollback(db)
        # Die Phase darf hier nicht auf `executing` festfrieren — sonst hält
        # `lifespan._emit_lifecycle_shutdown()` jeden künftigen Shutdown für
        # einen laufenden geplanten Neustart und unterdrückt dessen Push
        # dauerhaft. Best-effort und muss selbst nie werfen.
        try:
            state = get_state(db)
            if state.phase == PHASE_EXECUTING:
                reset_to_idle(db, state)
        except Exception as reset_exc:
            logger.warning(
                "Zurücksetzen der Phase nach fehlgeschlagener Boot-Auswertung "
                "fehlgeschlagen: %s", reset_exc,
            )
            _safe_rollback(db)
        return None


def should_defer_suspend(db: Session, sleep_service: "SleepManagerService") -> bool:
    """Ob ein automatischer Suspend zugunsten eines scharfen Neustarts ausfällt.

    Nur wenn die Gates offen sind — sonst würde ein blockierter Termin die Box
    bis zum Ablauf der Frist wachhalten und Strom verbrennen.
    """
    try:
        state = get_state(db)
        if state.phase != PHASE_ARMED:
            return False
        return gates_blocking(db, sleep_service, state.execution_id) is None
    except Exception as exc:
        logger.warning("Suspend-Verdrängung nicht prüfbar: %s", exc)
        return False


def reset_before_suspend(db: Session) -> None:
    """Vor einem Suspend, der trotz `armed` stattfindet, aufräumen.

    Sonst stünde `phase=armed` mit einem `due_at` von gestern da, während die
    Weckzeit schon auf den Termin nächster Woche zeigt.
    """
    try:
        state = get_state(db)
        if state.phase != PHASE_ARMED:
            return
        reason = state.last_skip_reason or SKIP_NOT_IDLE
        close_execution(
            db, state.execution_id, SchedulerStatus.CANCELLED.value,
            error=SKIP_REASON_LABELS.get(reason, reason),
        )
        reset_to_idle(db, state, completed_due_at=state.due_at)
    except Exception as exc:
        logger.warning("Zurücksetzen vor dem Suspend fehlgeschlagen: %s", exc)
        _safe_rollback(db)


def resuspend_target(db: Session) -> tuple[bool, Optional[datetime]]:
    """`(ist ein Wieder-Suspend fällig, wake_at)` für den Sleep-Loop.

    `wake_at` ist **naiv server-lokal** — die Form, die `enter_true_suspend`
    erwartet und die `_next_occurrence`/`next_core_uptime_start` liefern.
    Gespeichert ist der Wert UTC-aware; roh durchgereicht käme er unter
    PostgreSQL aware und unter SQLite naiv-UTC an, und der Aufrufer läge im
    zweiten Fall um den UTC-Offset daneben. `to_local` deckt beide Backends ab
    (naive DB-Werte gelten dort als UTC, wie überall in diesem Modul).
    """
    try:
        state = get_state(db)
        if state.phase != PHASE_RESUSPEND_PENDING:
            return False, None
        stored = state.resuspend_wake_at
        return True, to_local(stored) if stored is not None else None
    except Exception:
        return False, None
