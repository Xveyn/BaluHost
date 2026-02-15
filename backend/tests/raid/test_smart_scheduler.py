import pytest

from app.core.config import settings
from app.services import smart as smart_service


def test_trigger_smart_test_api_admin(client, admin_headers):
    url = f"{settings.api_prefix}/system/smart/test"
    payload = {"device": "/dev/sda", "type": "short"}
    resp = client.post(url, json=payload, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "message" in data


def test_start_stop_smart_scheduler_respects_settings():
    old = getattr(settings, "smart_scan_enabled", False)
    try:
        settings.smart_scan_enabled = True
        smart_service.start_smart_scheduler()
        smart_service.stop_smart_scheduler()
    finally:
        settings.smart_scan_enabled = old
