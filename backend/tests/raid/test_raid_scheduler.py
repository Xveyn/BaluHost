import pytest

from app.core.config import settings
from app.services import raid as raid_service


def test_trigger_raid_scrub_api(client, admin_headers):
    url = f"{settings.api_prefix}/system/raid/scrub"
    resp = client.post(url, json={}, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "message" in data


def test_start_stop_scrub_scheduler_respects_settings():
    # Ensure enabling scheduler doesn't raise even if APScheduler missing
    old = getattr(settings, "raid_scrub_enabled", False)
    try:
        settings.raid_scrub_enabled = True
        # Should not raise even if APScheduler isn't installed in CI
        raid_service.start_scrub_scheduler()
        raid_service.stop_scrub_scheduler()
    finally:
        settings.raid_scrub_enabled = old
