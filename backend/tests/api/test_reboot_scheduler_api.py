"""API-Oberfläche des geplanten Systemneustarts."""
import json
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.models.scheduler_history import SchedulerConfig
from app.models.sleep import CoreUptimeWindow, SleepConfig
from app.services.audit.logger_db import ADMIN_ONLY_EVENTS

PREVIEW = "/api/schedulers/system_reboot/preview"


def _enable(db, **extra):
    payload = {"weekday": 6, "time": "04:00", "retry_window_hours": 6}
    payload.update(extra)
    db.add(SchedulerConfig(
        scheduler_name="system_reboot", is_enabled=True,
        interval_seconds=604800, extra_config=json.dumps(payload),
    ))
    db.commit()


def _core_uptime(db, *, master=True, **window):
    """Ein Kernbetriebszeit-Fenster PLUS dem Hauptschalter.

    Beides ist nötig: der Automat fragt über `_load_core_uptime()`, das bei
    ausgeschaltetem `core_uptime_enabled` `(False, [])` liefert. Ein Test, der
    nur die Fensterzeile anlegt, prüft eine Kollision, die es real nicht gibt.
    """
    payload = {"enabled": True, "label": "Wochentags", "start_time": "08:00",
               "end_time": "22:00", "weekdays": "0,1,2,3,4"}
    payload.update(window)
    db.add(SleepConfig(id=1, core_uptime_enabled=master))
    db.add(CoreUptimeWindow(**payload))
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


def test_config_without_a_toggle_does_not_arm_the_feature(
    client: TestClient, admin_headers: dict, db_session
):
    """„Default aus" ist die zentrale Sicherheitseigenschaft dieses Schedulers.

    Legte ein reiner Konfigurations-PUT die Zeile mit `is_enabled=True` an,
    schärfte das Speichern eines Wochentags ein Feature, das die Box neu
    startet — ohne dass jemand den Schalter angefasst hat.
    """
    resp = client.put(
        "/api/schedulers/system_reboot/config",
        json={"extra_config": {"weekday": 2, "time": "03:30"}},
        headers=admin_headers,
    )
    assert resp.status_code == 200

    row = db_session.query(SchedulerConfig).filter(
        SchedulerConfig.scheduler_name == "system_reboot"
    ).first()
    assert row is not None
    assert row.is_enabled is False


def test_config_without_a_toggle_still_enables_other_schedulers(
    client: TestClient, admin_headers: dict, db_session
):
    """Gegenprobe: das Verhalten aller anderen Scheduler bleibt unverändert."""
    resp = client.put(
        "/api/schedulers/backup/config",
        json={"interval_seconds": 7200},
        headers=admin_headers,
    )
    assert resp.status_code == 200

    row = db_session.query(SchedulerConfig).filter(
        SchedulerConfig.scheduler_name == "backup"
    ).first()
    assert row is not None
    assert row.is_enabled is True


def test_config_with_an_explicit_toggle_still_enables_the_reboot(
    client: TestClient, admin_headers: dict, db_session
):
    """Wer den Schalter mitsendet, bekommt was er sendet."""
    resp = client.put(
        "/api/schedulers/system_reboot/config",
        json={"is_enabled": True, "extra_config": {"weekday": 2, "time": "03:30"}},
        headers=admin_headers,
    )
    assert resp.status_code == 200

    row = db_session.query(SchedulerConfig).filter(
        SchedulerConfig.scheduler_name == "system_reboot"
    ).first()
    assert row.is_enabled is True


def test_preview_requires_admin(client: TestClient, user_headers: dict):
    resp = client.get("/api/schedulers/system_reboot/preview", headers=user_headers)
    assert resp.status_code == 403


def test_preview_reports_no_collision(client: TestClient, admin_headers: dict, db_session):
    _enable(db_session)
    body = client.get(PREVIEW, headers=admin_headers).json()
    assert body["enabled"] is True
    assert body["computed_from_parameters"] is False
    assert body["in_core_uptime"] is False
    assert body["reachable"] is True
    assert body["next_due_at"] is not None


def test_preview_reports_an_unreachable_collision(client: TestClient, admin_headers: dict, db_session):
    """Termin im Fenster, Fenster endet nach der Frist -> läuft nie."""
    _enable(db_session, weekday=0, time="10:00", retry_window_hours=6)
    _core_uptime(db_session)

    body = client.get(PREVIEW, headers=admin_headers).json()
    assert body["in_core_uptime"] is True
    assert body["reachable"] is False
    assert body["window_label"] == "Wochentags"


def test_preview_reports_a_reachable_collision(client: TestClient, admin_headers: dict, db_session):
    """Fenster endet innerhalb der Frist -> wird nachgeholt."""
    _enable(db_session, weekday=0, time="10:00", retry_window_hours=12)
    _core_uptime(db_session, label="Vormittag", end_time="12:00")

    body = client.get(PREVIEW, headers=admin_headers).json()
    assert body["in_core_uptime"] is True
    assert body["reachable"] is True


def test_preview_honours_the_core_uptime_master_switch(client: TestClient, admin_headers: dict, db_session):
    """Hauptschalter aus, Fensterzeilen noch da -> keine Kollision.

    Der Automat fragt über `_load_core_uptime()`, das bei ausgeschaltetem
    `core_uptime_enabled` `(False, [])` liefert und Gate 1 ganz abschaltet.
    Wertete die Vorschau die Zeilen trotzdem aus, behauptete sie „läuft so
    nie", während der Neustart in Wahrheit problemlos durchläuft.
    """
    _enable(db_session, weekday=0, time="10:00", retry_window_hours=6)
    _core_uptime(db_session, master=False)

    body = client.get(PREVIEW, headers=admin_headers).json()
    assert body["in_core_uptime"] is False
    assert body["reachable"] is True
    assert body["window_label"] is None


# --- Vorschau mit ungespeicherten Formularwerten --------------------------

def test_preview_with_parameters_warns_while_the_schedule_is_still_off(
    client: TestClient, admin_headers: dict, db_session
):
    """DER Hauptfall der Warnung: Feature aus, Admin richtet gerade ein.

    Ohne Parameter liefert `load_enabled_config()` hier `None` und damit
    `enabled=false, in_core_uptime=false` — die Warnung könnte in genau dem
    Moment, für den sie existiert, nie erscheinen.
    """
    _core_uptime(db_session)  # kein _enable() — der Zeitplan ist aus

    body = client.get(
        PREVIEW,
        params={"weekday": 0, "time": "10:00", "retry_window_hours": 6},
        headers=admin_headers,
    ).json()

    assert body["computed_from_parameters"] is True
    assert body["in_core_uptime"] is True
    assert body["reachable"] is False
    # `enabled` meint weiterhin den GESPEICHERTEN Zustand.
    assert body["enabled"] is False


def test_preview_parameters_beat_the_saved_configuration(
    client: TestClient, admin_headers: dict, db_session
):
    """Gespeichert 04:00 (kollisionsfrei), im Formular 09:00 (mitten im Fenster)."""
    _enable(db_session, weekday=0, time="04:00", retry_window_hours=6)
    _core_uptime(db_session)

    saved = client.get(PREVIEW, headers=admin_headers).json()
    assert saved["in_core_uptime"] is False

    typed = client.get(
        PREVIEW, params={"weekday": 0, "time": "09:00"}, headers=admin_headers
    ).json()
    assert typed["in_core_uptime"] is True
    assert typed["enabled"] is True
    assert typed["computed_from_parameters"] is True


def test_preview_keeps_unset_fields_from_the_saved_configuration(
    client: TestClient, admin_headers: dict, db_session
):
    """Nur die Uhrzeit umgestellt -> der gespeicherte Wochentag bleibt."""
    _enable(db_session, weekday=0, time="04:00", retry_window_hours=6)
    _core_uptime(db_session, weekdays="0")  # nur Montag

    body = client.get(
        PREVIEW, params={"time": "09:00"}, headers=admin_headers
    ).json()
    assert body["in_core_uptime"] is True


def test_preview_rejects_an_invalid_parameter(client: TestClient, admin_headers: dict, db_session):
    """Dieselben Regeln wie beim Speichern — eine Definition, nicht zwei."""
    _enable(db_session)
    assert client.get(
        PREVIEW, params={"weekday": 9}, headers=admin_headers
    ).status_code == 422
    assert client.get(
        PREVIEW, params={"time": "25:00"}, headers=admin_headers
    ).status_code == 422
    assert client.get(
        PREVIEW, params={"retry_window_hours": 99}, headers=admin_headers
    ).status_code == 422


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


def test_reboot_audit_events_stay_admin_only(client: TestClient, admin_headers: dict):
    """update_reboot_schedule und toggle_reboot_schedule dürfen für normale
    Nutzer nicht im Audit-Log sichtbar werden — die Sichtfilterung in
    `routes/logging.py` entscheidet allein über `ADMIN_ONLY_EVENTS`
    (Groß-/Kleinschreibung ist dabei relevant: die Menge enthält 'ADMIN',
    nicht 'admin'). Importiert die Menge statt den String zu wiederholen,
    damit der Test mitdriftet, wenn sie sich ändert.
    """
    mock_logger = MagicMock()
    with patch("app.api.routes.schedulers.get_audit_logger_db", return_value=mock_logger):
        config_resp = client.put(
            "/api/schedulers/system_reboot/config",
            json={"extra_config": {"weekday": 1, "time": "02:00"}},
            headers=admin_headers,
        )
        toggle_resp = client.post(
            "/api/schedulers/system_reboot/toggle",
            json={"enabled": True},
            headers=admin_headers,
        )

    assert config_resp.status_code == 200
    assert toggle_resp.status_code == 200
    assert mock_logger.log_event.call_count == 2

    for call in mock_logger.log_event.call_args_list:
        assert call.kwargs.get("event_type") in ADMIN_ONLY_EVENTS
