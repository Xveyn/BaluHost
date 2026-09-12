"""system_reboot ist ein Registry-Eintrag OHNE APScheduler-Job."""
from unittest.mock import MagicMock

from app.schemas.scheduler import SCHEDULER_REGISTRY
from app.services.scheduler.worker import SchedulerWorker


def test_registry_entry_exists_and_declares_no_worker_job():
    entry = SCHEDULER_REGISTRY["system_reboot"]
    assert entry["worker_job"] is False
    assert entry["can_run_manually"] is False


def test_every_other_entry_keeps_its_worker_job():
    """Der info.get(..., True)-Default darf nichts anderes abschalten."""
    for name, info in SCHEDULER_REGISTRY.items():
        if name == "system_reboot":
            continue
        assert info.get("worker_job", True) is True, name


def test_worker_does_not_schedule_a_job_for_system_reboot(monkeypatch):
    worker = SchedulerWorker()
    worker.scheduler = MagicMock()
    added: list[str] = []
    monkeypatch.setattr(
        worker, "_add_job", lambda name, interval: added.append(name)
    )
    monkeypatch.setattr(worker, "_is_scheduler_enabled", lambda name, db: True)
    monkeypatch.setattr(worker, "_get_interval", lambda name, info, db: 3600)
    monkeypatch.setattr(
        "app.services.scheduler.worker.SessionLocal", lambda: MagicMock()
    )

    worker._load_and_schedule_jobs()

    assert "system_reboot" not in added
    assert "raid_scrub" in added  # Gegenprobe: alles andere läuft weiter


def test_worker_writes_no_heartbeat_row_for_system_reboot(monkeypatch):
    """Sonst zeigt die Dashboard-Karte einen erfundenen Gesundheitszustand."""
    worker = SchedulerWorker()
    worker.scheduler = MagicMock()
    worker.scheduler.get_job.return_value = None

    seen: list[str] = []

    class _Query:
        def filter(self, *a, **k):
            return self

        def first(self):
            return None

    class _DB:
        def query(self, *a, **k):
            return _Query()

        def add(self, obj):
            seen.append(obj.scheduler_name)

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr("app.services.scheduler.worker.SessionLocal", lambda: _DB())
    monkeypatch.setattr(
        "app.services.scheduler.worker.commit_with_retry", lambda db: None, raising=False
    )

    worker._update_all_heartbeats()

    assert "system_reboot" not in seen


def test_service_reports_system_reboot_disabled_without_config(db_session):
    from app.services.scheduler.service import SchedulerService

    service = SchedulerService(db_session)
    assert service._check_scheduler_enabled("system_reboot") is False
