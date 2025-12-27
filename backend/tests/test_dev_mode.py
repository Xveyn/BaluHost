from __future__ import annotations

import os
from typing import Generator

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("NAS_MODE", "dev")
os.environ.setdefault("NAS_QUOTA_BYTES", str(10 * 1024 * 1024 * 1024))

from app.main import app  # noqa: E402 (import after env setup)
from app.core.config import settings
from scripts.reset_dev_storage import reset_dev_storage


@pytest.fixture(scope="function")
def client(db_session) -> Generator[TestClient, None, None]:
    reset_dev_storage()

    # Override DB dependency to use the test in-memory session
    from app.core.database import get_db
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    # Ensure admin exists in the test DB
    from app.services import users as user_service
    from app.schemas.user import UserCreate
    if not user_service.get_user_by_username(settings.admin_username, db=db_session):
        user_service.create_user(
            UserCreate(
                username=settings.admin_username,
                email=settings.admin_email,
                password=settings.admin_password,
                role=settings.admin_role,
            ),
            db=db_session,
        )

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    reset_dev_storage()


def _login(client: TestClient, username: str = "admin", password: str = "changeme") -> str:
    response = client.post(
        f"{settings.api_prefix}/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    return data["access_token"]


def test_quota_endpoint(client: TestClient) -> None:
    token = _login(client)
    response = client.get(
        f"{settings.api_prefix}/system/quota",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["limit_bytes"] == settings.nas_quota_bytes
    assert payload["used_bytes"] >= 0
    assert payload["percent_used"] is None or payload["percent_used"] >= 0


def test_system_info_dev_mode(client: TestClient) -> None:
    token = _login(client)
    response = client.get(
        f"{settings.api_prefix}/system/info",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["uptime"] == pytest.approx(4 * 3600.0)
    assert payload["cpu"]["usage"] == pytest.approx(18.5)
    assert payload["cpu"]["cores"] >= 1
    assert payload["memory"]["total"] == 8 * 1024 ** 3
    assert payload["disk"]["total"] == settings.nas_quota_bytes


def test_storage_info_matches_quota(client: TestClient) -> None:
    token = _login(client)
    response = client.get(
        f"{settings.api_prefix}/system/storage",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["filesystem"] == "baluhost-dev"
    assert payload["total"] == settings.nas_quota_bytes
    assert payload["mount_point"] == settings.nas_storage_path
    assert payload["use_percent"].endswith("%")


def test_process_list_limit(client: TestClient) -> None:
    token = _login(client)
    response = client.get(
        f"{settings.api_prefix}/system/processes",
        params={"limit": 5},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()

    assert "processes" in payload
    assert len(payload["processes"]) <= 5


def test_raid_simulation_cycle(client: TestClient) -> None:
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    status_resp = client.get(f"{settings.api_prefix}/system/raid/status", headers=headers)
    assert status_resp.status_code == 200
    arrays = status_resp.json()["arrays"]
    assert arrays, "Expected at least one simulated RAID array"
    array_name = arrays[0]["name"]
    expected_capacity = settings.nas_quota_bytes or 10 * 1024 ** 3
    assert arrays[0]["size_bytes"] == expected_capacity

    degrade_resp = client.post(
        f"{settings.api_prefix}/system/raid/degrade",
        json={"array": array_name},
        headers=headers,
    )
    assert degrade_resp.status_code == 200

    degraded_status = client.get(f"{settings.api_prefix}/system/raid/status", headers=headers)
    assert degraded_status.status_code == 200
    assert degraded_status.json()["arrays"][0]["status"] == "degraded"

    rebuild_resp = client.post(
        f"{settings.api_prefix}/system/raid/rebuild",
        json={"array": array_name},
        headers=headers,
    )
    assert rebuild_resp.status_code == 200

    rebuilding_status = client.get(f"{settings.api_prefix}/system/raid/status", headers=headers)
    assert rebuilding_status.status_code == 200
    assert rebuilding_status.json()["arrays"][0]["status"] == "rebuilding"

    finalize_resp = client.post(
        f"{settings.api_prefix}/system/raid/finalize",
        json={"array": array_name},
        headers=headers,
    )
    assert finalize_resp.status_code == 200

    final_status = client.get(f"{settings.api_prefix}/system/raid/status", headers=headers)
    assert final_status.status_code == 200
    assert final_status.json()["arrays"][0]["status"] == "optimal"


def test_smart_status(client: TestClient) -> None:
    token = _login(client)
    response = client.get(
        f"{settings.api_prefix}/system/smart/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "devices" in payload
    assert payload["devices"], "Expected at least one mock SMART device"


def test_raid_configuration_options(client: TestClient) -> None:
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    status_resp = client.get(f"{settings.api_prefix}/system/raid/status", headers=headers)
    assert status_resp.status_code == 200
    array = status_resp.json()["arrays"][0]
    array_name = array["name"]

    # Toggle bitmap off
    resp = client.post(
        f"{settings.api_prefix}/system/raid/options",
        headers=headers,
        json={"array": array_name, "enable_bitmap": False},
    )
    assert resp.status_code == 200

    status = client.get(f"{settings.api_prefix}/system/raid/status", headers=headers)
    assert status.status_code == 200
    updated = status.json()["arrays"][0]
    assert updated["bitmap"] is None

    # Add spare and mark device write-mostly
    resp = client.post(
        f"{settings.api_prefix}/system/raid/options",
        headers=headers,
        json={
            "array": array_name,
            "add_spare": "sdc1",
            "write_mostly_device": "sda1",
            "write_mostly": True,
            "set_speed_limit_min": 1500,
            "set_speed_limit_max": 6000,
            "trigger_scrub": True,
        },
    )
    assert resp.status_code == 200

    status = client.get(f"{settings.api_prefix}/system/raid/status", headers=headers)
    data = status.json()
    devices = {dev["name"]: dev for dev in data["arrays"][0]["devices"]}
    assert devices["sda1"]["state"] == "write-mostly"
    assert devices["sdc1"]["state"] == "spare"
    assert data["arrays"][0]["sync_action"] == "check"
    limits = data.get("speed_limits")
    assert limits["minimum"] == 1500
    assert limits["maximum"] == 6000