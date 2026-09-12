"""Die vier Gates des geplanten Systemneustarts."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models.scheduler_history import SchedulerExecution, SchedulerStatus
from app.services.power import scheduled_reboot
from app.services.power.scheduled_reboot import (
    SKIP_CORE_UPTIME,
    SKIP_DISPLAYS,
    SKIP_NOT_IDLE,
    SKIP_REASON_LABELS,
    SKIP_SCHEDULER_JOB,
    SKIP_UNREADABLE,
    gates_blocking,
)


def _sleep_service(*, in_core=False, idle=True):
    svc = MagicMock()
    svc._load_config.return_value = SimpleNamespace(idle_cpu_threshold=5.0)
    svc._load_core_uptime.return_value = (in_core, [])
    svc._is_system_idle.return_value = idle
    svc._get_activity_metrics.return_value = SimpleNamespace()
    return svc


@pytest.fixture(autouse=True)
def _displays_off(request, monkeypatch):
    """Hält `displays_block()` für die Gate-Tests neutral (False).

    Ausgenommen sind die beiden Tests, die `displays_block()` selbst prüfen —
    für die darf die echte Funktion nicht überschrieben sein, sonst testen sie
    nur noch den Mock.
    """
    if request.node.name.startswith("test_displays_block_is_"):
        return
    monkeypatch.setattr(scheduled_reboot, "displays_block", lambda: False)


def test_all_gates_open(db_session):
    assert gates_blocking(db_session, _sleep_service(), None) is None


def test_core_uptime_blocks(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.power.scheduled_reboot.core_uptime_helpers.is_in_core_uptime",
        lambda now, windows: (True, object()),
    )
    svc = _sleep_service()
    svc._load_core_uptime.return_value = (True, [object()])
    assert gates_blocking(db_session, svc, None) == SKIP_CORE_UPTIME


def test_displays_block(db_session, monkeypatch):
    monkeypatch.setattr(scheduled_reboot, "displays_block", lambda: True)
    assert gates_blocking(db_session, _sleep_service(), None) == SKIP_DISPLAYS


def test_running_scheduler_job_blocks(db_session):
    db_session.add(
        SchedulerExecution(
            scheduler_name="backup",
            trigger_type="scheduled",
            started_at=datetime.now(timezone.utc),
            status=SchedulerStatus.RUNNING.value,
        )
    )
    db_session.commit()
    assert gates_blocking(db_session, _sleep_service(), None) == SKIP_SCHEDULER_JOB


def test_own_execution_row_does_not_block(db_session):
    """Die eigene 'running'-Zeile darf sich nicht selbst blockieren."""
    own = SchedulerExecution(
        scheduler_name="system_reboot",
        trigger_type="scheduled",
        started_at=datetime.now(timezone.utc),
        status=SchedulerStatus.RUNNING.value,
    )
    db_session.add(own)
    db_session.commit()
    assert gates_blocking(db_session, _sleep_service(), own.id) is None


def test_busy_system_blocks(db_session):
    """Gate 4 ist _is_system_idle, nicht nur active_uploads — ein SMB-Transfer
    schlägt über den Disk-I/O-Wert an und würde sonst durchrutschen."""
    svc = _sleep_service(idle=False)
    assert gates_blocking(db_session, svc, None) == SKIP_NOT_IDLE
    # Ohne diese Zusicherung würde der Test auch grün bleiben, wenn Gate 4
    # fälschlich `active_uploads` läse: der resultierende AttributeError liefe
    # in denselben except-Zweig und lieferte zufällig denselben Grund.
    svc._is_system_idle.assert_called_once()


def test_gate_order_core_uptime_wins(db_session, monkeypatch):
    """Erster Treffer gewinnt — die Reihenfolge ist Teil der Meldung."""
    monkeypatch.setattr(scheduled_reboot, "displays_block", lambda: True)
    svc = _sleep_service(idle=False)
    svc._load_core_uptime.return_value = (True, [object()])
    monkeypatch.setattr(
        "app.services.power.scheduled_reboot.core_uptime_helpers.is_in_core_uptime",
        lambda now, windows: (True, object()),
    )
    assert gates_blocking(db_session, svc, None) == SKIP_CORE_UPTIME


def test_db_unreachable_blocks(monkeypatch):
    """Erreichbarkeitsprüfung: eine werfende DB-Abfrage blockiert geschlossen,
    statt dass ein einzelnes Gate (das den Fehler nie zu sehen bekommt, weil
    seine Helfer eigene Fehler schlucken) ihn stillschweigend verschluckt."""
    bad_db = MagicMock()
    bad_db.query.side_effect = OSError("db down")
    assert gates_blocking(bad_db, _sleep_service(), None) == SKIP_UNREADABLE


def test_missing_sleep_config_does_not_block_alone(db_session):
    """config is None ist der Normalfall auf einer Box, auf der nie jemand die
    Schlafeinstellungen gespeichert hat (sleep_config wird ausschließlich von
    update_config() angelegt) — kein Fehlerfall, also kein Blockieren."""
    svc = _sleep_service()
    svc._load_config.return_value = None
    assert gates_blocking(db_session, svc, None) is None
    svc._is_system_idle.assert_not_called()


def test_missing_sleep_config_skips_gate_four_but_others_still_run(db_session, monkeypatch):
    """Ohne Config gibt es keine Schwellen und damit keine Definition von
    'idle' — Gate 4 wird übersprungen, aber die anderen drei Gates greifen
    unverändert weiter."""
    monkeypatch.setattr(scheduled_reboot, "displays_block", lambda: True)
    svc = _sleep_service()
    svc._load_config.return_value = None
    assert gates_blocking(db_session, svc, None) == SKIP_DISPLAYS
    svc._is_system_idle.assert_not_called()


def test_every_reason_has_a_label():
    for reason in (
        SKIP_CORE_UPTIME,
        SKIP_DISPLAYS,
        SKIP_SCHEDULER_JOB,
        SKIP_NOT_IDLE,
        SKIP_UNREADABLE,
    ):
        assert SKIP_REASON_LABELS[reason]


def test_displays_block_is_false_in_dev_mode(monkeypatch):
    """gaming_presence.displays_on() liefert im Dev-Mode hart True. Würden wir
    die Funktion hier wiederverwenden, wäre das Feature lokal nie auslösbar."""
    monkeypatch.setattr(
        "app.services.power.scheduled_reboot.settings.is_dev_mode", True, raising=False
    )
    assert scheduled_reboot.displays_block() is False


def test_displays_block_is_true_when_unreadable(monkeypatch):
    """Unwissen blockiert — Gegenrichtung zum Gaming-Gate, weil ein Neustart
    die eingreifendere Aktion ist."""
    monkeypatch.setattr(
        "app.services.power.scheduled_reboot.settings.is_dev_mode", False, raising=False
    )

    def _boom():
        raise OSError("kein DRM")

    monkeypatch.setattr(
        "app.services.power.scheduled_reboot.get_active_display_count_sync", _boom
    )
    assert scheduled_reboot.displays_block() is True
