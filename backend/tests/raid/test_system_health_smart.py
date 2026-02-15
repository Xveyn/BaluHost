import pytest

from app.core.config import settings


def test_system_health_endpoint(client, user_headers):
    url = f"{settings.api_prefix}/system/health"
    resp = client.get(url, headers=user_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("status") == "ok"
    assert "system" in data
    # smart and raid may be None in some environments, but disk_io should be present
    assert "disk_io" in data


@pytest.mark.usefixtures("admin_headers")
def test_trigger_smart_test_admin(client, admin_headers):
    url = f"{settings.api_prefix}/system/smart/test"
    payload = {"device": "/dev/sda", "type": "short"}
    resp = client.post(url, json=payload, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "message" in data
    assert "SMART" in data["message"] or "Simulated" in data["message"]
