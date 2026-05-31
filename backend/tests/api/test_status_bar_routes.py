"""Integration tests for /api/system/statusbar endpoints."""
import pytest
from fastapi.testclient import TestClient


def test_get_config_requires_admin(client: TestClient, user_headers):
    r = client.get("/api/system/statusbar/config", headers=user_headers)
    assert r.status_code == 403


def test_get_config_as_admin_returns_catalog(client: TestClient, admin_headers):
    r = client.get("/api/system/statusbar/config", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body["pills"]) == 12
    assert "show_bottom_upload" in body


def test_get_state_requires_auth(client: TestClient):
    r = client.get("/api/system/statusbar/state")
    assert r.status_code in (401, 403)  # match project's no-token convention


def test_get_state_as_user_returns_payload(client: TestClient, user_headers):
    r = client.get("/api/system/statusbar/state", headers=user_headers)
    assert r.status_code == 200
    assert "pills" in r.json()


def test_put_config_rejects_locked_all_visibility(client: TestClient, admin_headers):
    payload = {
        "pills": [{"pill_id": "raid", "enabled": True, "visibility": "all", "sort_order": 0}],
        "show_bottom_upload": True,
    }
    r = client.put("/api/system/statusbar/config", json=payload, headers=admin_headers)
    assert r.status_code == 400


def test_put_config_as_user_forbidden(client: TestClient, user_headers):
    payload = {"pills": [], "show_bottom_upload": True}
    r = client.put("/api/system/statusbar/config", json=payload, headers=user_headers)
    assert r.status_code == 403


def test_put_config_writes_audit_log(client: TestClient, admin_headers, db_session):
    from app.models.audit_log import AuditLog

    payload = {
        "pills": [{"pill_id": "power", "enabled": True, "visibility": "all", "sort_order": 0}],
        "show_bottom_upload": True,
    }
    r = client.put("/api/system/statusbar/config", json=payload, headers=admin_headers)
    assert r.status_code == 200

    logged = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "status_bar.config_changed")
        .count()
    )
    assert logged >= 1


def test_put_config_rejects_display_mode_on_non_configurable_pill(client: TestClient, admin_headers):
    cfg = client.get("/api/system/statusbar/config", headers=admin_headers).json()
    pills = [{
        "pill_id": p["pill_id"], "enabled": p["enabled"], "visibility": p["visibility"],
        "sort_order": p["sort_order"],
        "display_mode": "when_off" if p["pill_id"] == "power" else "always",
    } for p in cfg["pills"]]
    r = client.put("/api/system/statusbar/config",
                   json={"pills": pills, "show_bottom_upload": True},
                   headers=admin_headers)
    assert r.status_code == 400


def test_put_config_accepts_display_mode_on_desktop(client: TestClient, admin_headers):
    cfg = client.get("/api/system/statusbar/config", headers=admin_headers).json()
    pills = [{
        "pill_id": p["pill_id"], "enabled": p["enabled"], "visibility": p["visibility"],
        "sort_order": p["sort_order"],
        "display_mode": "when_off" if p["pill_id"] == "desktop" else "always",
    } for p in cfg["pills"]]
    r = client.put("/api/system/statusbar/config",
                   json={"pills": pills, "show_bottom_upload": True},
                   headers=admin_headers)
    assert r.status_code == 200
    desktop = next(p for p in r.json()["pills"] if p["pill_id"] == "desktop")
    assert desktop["display_mode"] == "when_off"
    assert desktop["display_mode_configurable"] is True
