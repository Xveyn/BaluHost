"""Restart/shutdown via API and scheduled syncs are audited in the DB (#727).

They went to the file-based AuditLogger (a daily file under nas_temp_path),
so the admin audit view - which reads audit_logs - never showed an API
restart or shutdown.
"""
import threading
from datetime import datetime, timedelta, timezone

import pytest


class _NoTimer:
    """Stands in for threading.Timer so the test process isn't restarted/killed."""

    def __init__(self, *args, **kwargs):
        self.daemon = False

    def start(self):
        pass


class _Recorder:
    def __init__(self):
        self.system: list[dict] = []
        self.events: list[dict] = []

    def log_system_event(self, **kwargs):
        self.system.append(kwargs)

    def log_event(self, **kwargs):
        self.events.append(kwargs)

    def log_security_event(self, **kwargs):
        pass


@pytest.fixture
def recorder(monkeypatch):
    import app.api.routes.system as system_routes

    rec = _Recorder()
    monkeypatch.setattr(system_routes, "get_audit_logger_db", lambda: rec)

    # Only system.py's view of threading: patching threading.Timer globally
    # leaks into the rate limiter's storage, which keeps the Timer it created
    # and later calls is_alive() on it.
    class _Threading:
        Timer = _NoTimer

        def __getattr__(self, name):
            return getattr(threading, name)

    monkeypatch.setattr(system_routes, "threading", _Threading())
    return rec


@pytest.mark.parametrize("path,action", [
    ("/api/system/restart", "restart_initiated"),
    ("/api/system/shutdown", "shutdown_initiated"),
])
def test_restart_and_shutdown_are_audited_in_the_db(client, admin_headers, recorder, path, action):
    r = client.post(path, headers=admin_headers)

    assert r.status_code == 200
    assert [e["action"] for e in recorder.system] == [action]
    assert recorder.system[0]["user"] == "admin"


def _schedule(db_session, device_id: str):
    from app.models.sync_progress import SyncSchedule
    from app.models.user import User

    user = db_session.query(User).filter(User.username == "admin").first()
    sched = SyncSchedule(
        user_id=user.id, device_id=device_id, schedule_type="daily", time_of_day="02:00",
        is_active=True, next_run_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    db_session.add(sched)
    db_session.commit()
    db_session.refresh(sched)
    return sched


def _run(coro):
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_scheduled_sync_skip_is_audited_in_the_db(client, db_session, monkeypatch):
    import app.services.sync.background as background

    rec = _Recorder()
    monkeypatch.setattr(background, "get_audit_logger_db", lambda: rec, raising=False)
    sched = _schedule(db_session, "ghost-device")

    _run(background.SyncBackgroundScheduler().execute_scheduled_sync(sched, db_session))

    assert [e["action"] for e in rec.events] == ["scheduled_sync_skipped"]
    assert rec.events[0]["event_type"] == "SYNC"


def test_scheduled_sync_failure_does_not_put_the_exception_text_in_the_entry(client, db_session, monkeypatch):
    # Non-admins see error_message in the audit view (details are hidden), so
    # the raw exception text must not end up there.
    import app.services.sync.background as background

    rec = _Recorder()
    monkeypatch.setattr(background, "get_audit_logger_db", lambda: rec, raising=False)

    def _boom(self, *a, **kw):
        raise RuntimeError("secret /srv/internal/path")

    monkeypatch.setattr(background.FileSyncService, "get_sync_status", _boom)
    sched = _schedule(db_session, "desk-1")

    with pytest.raises(RuntimeError):
        _run(background.SyncBackgroundScheduler().execute_scheduled_sync(sched, db_session))

    failed = rec.events[-1]
    assert failed["action"] == "scheduled_sync_failed"
    assert failed["success"] is False
    assert "secret" not in str(failed.get("error_message"))
    assert "secret" not in str(failed.get("details"))
    assert failed["error_message"] == "RuntimeError"
