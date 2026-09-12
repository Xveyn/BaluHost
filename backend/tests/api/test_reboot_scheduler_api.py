"""API-Oberfläche des geplanten Systemneustarts."""
import json

from fastapi.testclient import TestClient

from app.models.scheduler_history import SchedulerConfig
from app.models.sleep import CoreUptimeWindow


def _enable(db, **extra):
    payload = {"weekday": 6, "time": "04:00", "retry_window_hours": 6}
    payload.update(extra)
    db.add(SchedulerConfig(
        scheduler_name="system_reboot", is_enabled=True,
        interval_seconds=604800, extra_config=json.dumps(payload),
    ))
    db.commit()


def test_config_rejects_an_invalid_weekday(client: TestClient, admin_headers: dict):
    resp = client.put(
        "/api/schedulers/system_reboot/config",
        json={"extra_config": {"weekday": 9, "time": "04:00"}},
        headers=admin_headers,
    )
    assert resp.status_code == 422


def test_config_rejects_an_invalid_time(client: TestClient, admin_headers: dict):
    resp = client.put(
        "/api/schedulers/system_reboot/config",
        json={"extra_config": {"weekday": 6, "time": "25:00"}},
        headers=admin_headers,
    )
    assert resp.status_code == 422


def test_config_accepts_valid_values(client: TestClient, admin_headers: dict):
    resp = client.put(
        "/api/schedulers/system_reboot/config",
        json={"extra_config": {"weekday": 2, "time": "03:30",
                               "retry_window_hours": 4, "warning_lead_minutes": 15}},
        headers=admin_headers,
    )
    assert resp.status_code == 200


def test_other_schedulers_keep_their_free_extra_config(client: TestClient, admin_headers: dict):
    """Die Validierung gilt nur für system_reboot."""
    resp = client.put(
        "/api/schedulers/backup/config",
        json={"extra_config": {"backup_type": "incremental"}},
        headers=admin_headers,
    )
    assert resp.status_code == 200


def test_preview_requires_admin(client: TestClient, user_headers: dict):
    resp = client.get("/api/schedulers/system_reboot/preview", headers=user_headers)
    assert resp.status_code == 403


def test_preview_reports_no_collision(client: TestClient, admin_headers: dict, db_session):
    _enable(db_session)
    body = client.get("/api/schedulers/system_reboot/preview", headers=admin_headers).json()
    assert body["enabled"] is True
    assert body["in_core_uptime"] is False
    assert body["reachable"] is True
    assert body["next_due_at"] is not None


def test_preview_reports_an_unreachable_collision(client: TestClient, admin_headers: dict, db_session):
    """Termin im Fenster, Fenster endet nach der Frist -> läuft nie."""
    _enable(db_session, weekday=0, time="10:00", retry_window_hours=6)
    db_session.add(CoreUptimeWindow(
        enabled=True, label="Wochentags", start_time="08:00",
        end_time="22:00", weekdays="0,1,2,3,4",
    ))
    db_session.commit()

    body = client.get("/api/schedulers/system_reboot/preview", headers=admin_headers).json()
    assert body["in_core_uptime"] is True
    assert body["reachable"] is False
    assert body["window_label"] == "Wochentags"


def test_preview_reports_a_reachable_collision(client: TestClient, admin_headers: dict, db_session):
    """Fenster endet innerhalb der Frist -> wird nachgeholt."""
    _enable(db_session, weekday=0, time="10:00", retry_window_hours=12)
    db_session.add(CoreUptimeWindow(
        enabled=True, label="Vormittag", start_time="08:00",
        end_time="12:00", weekdays="0,1,2,3,4",
    ))
    db_session.commit()

    body = client.get("/api/schedulers/system_reboot/preview", headers=admin_headers).json()
    assert body["in_core_uptime"] is True
    assert body["reachable"] is True


def test_status_has_a_next_run_without_any_worker_state(client: TestClient, admin_headers: dict, db_session):
    _enable(db_session)
    body = client.get("/api/schedulers/system_reboot", headers=admin_headers).json()
    assert body["next_run_at"] is not None
    assert body["worker_healthy"] is None
    assert "04:00" in body["interval_display"]


def test_status_has_no_next_run_when_disabled(client: TestClient, admin_headers: dict):
    body = client.get("/api/schedulers/system_reboot", headers=admin_headers).json()
    assert body["is_enabled"] is False
    assert body["next_run_at"] is None
