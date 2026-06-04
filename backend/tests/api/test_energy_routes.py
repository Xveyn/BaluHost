"""API integration tests for energy cumulative custom-range params."""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

from app.models.smart_device import SmartDevice


def _iso(dt: datetime) -> str:
    """Return an ISO string safe for use in query strings (Z suffix, no +00:00)."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


@pytest.fixture
def power_device(db_session) -> SmartDevice:
    device = SmartDevice(
        name="Route Test Plug", plugin_name="tapo_smart_plug",
        device_type_id="tapo_p110", address="192.168.1.50",
        capabilities=["power_monitor"], is_active=True, is_online=True,
        created_by_user_id=1,
    )
    db_session.add(device)
    db_session.commit()
    db_session.refresh(device)
    return device


class TestCumulativeRangeParams:
    def test_requires_auth(self, client: TestClient, power_device):
        r = client.get(f"/api/energy/cumulative/{power_device.id}?period=today")
        assert r.status_code == 401

    def test_one_sided_range_rejected(self, client: TestClient, user_headers, power_device):
        start = _iso(datetime.now(timezone.utc))
        qs = urlencode({"start": start})
        r = client.get(
            f"/api/energy/cumulative/{power_device.id}?{qs}",
            headers=user_headers,
        )
        assert r.status_code == 422

    def test_reversed_range_rejected(self, client: TestClient, user_headers, power_device):
        now = datetime.now(timezone.utc)
        qs = urlencode({"start": _iso(now), "end": _iso(now - timedelta(days=1))})
        r = client.get(
            f"/api/energy/cumulative/{power_device.id}?{qs}",
            headers=user_headers,
        )
        assert r.status_code == 422

    def test_valid_empty_range_returns_custom(self, client: TestClient, user_headers, power_device):
        now = datetime.now(timezone.utc)
        qs = urlencode({
            "start": _iso(now - timedelta(days=400)),
            "end": _iso(now - timedelta(days=399)),
        })
        r = client.get(
            f"/api/energy/cumulative/{power_device.id}?{qs}",
            headers=user_headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["period"] == "custom"
        assert body["total_kwh"] == 0.0
        # empty custom window returns two synthetic 0 boundary points (start, end)
        assert len(body["data_points"]) == 2

    def test_total_valid_empty_range(self, client: TestClient, user_headers, power_device):
        now = datetime.now(timezone.utc)
        qs = urlencode({
            "start": _iso(now - timedelta(days=400)),
            "end": _iso(now - timedelta(days=399)),
        })
        r = client.get(
            f"/api/energy/cumulative/total?{qs}",
            headers=user_headers,
        )
        assert r.status_code == 200
        assert r.json()["period"] == "custom"
