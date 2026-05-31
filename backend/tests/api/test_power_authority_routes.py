"""Tests for /api/power authority endpoints (local-channel gated)."""
import pytest


def test_put_authority_requires_local_channel(remote_client, admin_headers):
    r = remote_client.put("/api/power/authority", json={"external_authority_enabled": True}, headers=admin_headers)
    assert r.status_code == 403
    assert r.json()["detail"]["error"] == "local_channel_required"


def test_get_authority_status_ok(client, admin_headers):
    r = client.get("/api/power/authority", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert "external_authority_enabled" in body
    assert "ppd_active" in body


def test_enable_authority_success_returns_200(client, admin_headers, monkeypatch):
    """The success path (acquire OK) must return 200 with the new status, not 500.

    Regression: update_authority used to `return await get_authority_status(...)`,
    calling a rate-limited route function directly. Now it uses a plain helper.
    """
    from app.services.power import config_store

    config_store.save_authority_config({"external_authority_enabled": False})

    async def fake_acquire():
        return True

    monkeypatch.setattr("app.services.power.ppd_authority.acquire", fake_acquire)
    monkeypatch.setattr("app.services.power.ppd_authority.status",
                        lambda: {"ppd_active": False, "ppd_masked": True})

    r = client.put("/api/power/authority", json={"external_authority_enabled": True}, headers=admin_headers)

    assert r.status_code == 200
    body = r.json()
    assert body["external_authority_enabled"] is True
    assert body["ppd_masked"] is True

    config_store.save_authority_config({"external_authority_enabled": False})


def test_enable_authority_fails_when_acquire_fails(client, admin_headers, monkeypatch):
    """If PPD can't be stood down, the flag must NOT be persisted (no split authority)."""
    from app.services.power import config_store

    config_store.save_authority_config({"external_authority_enabled": False})

    async def fake_acquire():
        return False

    monkeypatch.setattr("app.services.power.ppd_authority.acquire", fake_acquire)

    r = client.put("/api/power/authority", json={"external_authority_enabled": True}, headers=admin_headers)

    assert r.status_code == 500
    assert config_store.load_authority_config()["external_authority_enabled"] is False


def test_boost_rule_crud_local(client, admin_headers):
    """Local channel: full CRUD cycle for boost rules must succeed."""
    r = client.post("/api/power/boost-rules",
                    json={"kind": "process_glob", "pattern": "lutris*", "label": "Lutris", "target_max_mhz": 3000},
                    headers=admin_headers)
    assert r.status_code == 200
    rule_id = r.json()["id"]

    r = client.get("/api/power/boost-rules", headers=admin_headers)
    assert any(x["id"] == rule_id for x in r.json()["rules"])

    r = client.delete(f"/api/power/boost-rules/{rule_id}", headers=admin_headers)
    assert r.status_code == 200


def test_boost_rule_create_remote_blocked(remote_client, admin_headers):
    """Remote channel: POST /boost-rules must be blocked with 403."""
    r = remote_client.post("/api/power/boost-rules",
                           json={"kind": "process_glob", "pattern": "lutris*", "label": "Lutris"},
                           headers=admin_headers)
    assert r.status_code == 403


def test_boost_now_local(client, admin_headers):
    """Local channel: POST /boost-now must succeed."""
    r = client.post("/api/power/boost-now", json={"duration_seconds": 60}, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["success"] is True


def test_boost_now_remote_blocked(remote_client, admin_headers):
    """Remote channel: POST /boost-now must be blocked with 403."""
    r = remote_client.post("/api/power/boost-now", json={"duration_seconds": 60}, headers=admin_headers)
    assert r.status_code == 403


def test_put_boost_rule_can_disable(client, admin_headers):
    """PUT with enabled=false must actually disable the rule (False is not dropped)."""
    r = client.post("/api/power/boost-rules",
                    json={"kind": "process_glob", "pattern": "foo*", "label": "Foo"},
                    headers=admin_headers)
    rule_id = r.json()["id"]

    r = client.put(f"/api/power/boost-rules/{rule_id}", json={"enabled": False}, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["enabled"] is False

    client.delete(f"/api/power/boost-rules/{rule_id}", headers=admin_headers)


def test_boost_now_passes_target_override(client, admin_headers, monkeypatch):
    """boost-now must forward the chosen target_max_mhz to register_demand."""
    from app.services.power.manager import get_power_manager

    captured = {}

    async def fake_register(source, level, **kw):
        captured["source"] = source
        captured.update(kw)
        return source

    monkeypatch.setattr(get_power_manager(), "register_demand", fake_register)

    r = client.post("/api/power/boost-now",
                    json={"duration_seconds": 120, "target_max_mhz": 2500},
                    headers=admin_headers)

    assert r.status_code == 200
    assert captured["source"] == "manual-boost"
    assert captured.get("max_freq_override") == 2500
    assert captured.get("timeout_seconds") == 120
