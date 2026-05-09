"""Schema-level tests for OsSleepReportResponse and the 7-day cap."""
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.schemas.sleep import (
    OsSleepIssueModel,
    OsSleepReportResponse,
    SleepConfigUpdate,
)


class TestOsSleepReportResponse:
    def test_minimal_payload_validates(self):
        payload = {"platform_supported": False}
        m = OsSleepReportResponse(**payload)
        assert m.platform_supported is False
        assert m.logind == {}
        assert m.issues == []
        assert m.sources == []

    def test_full_payload_round_trip(self):
        payload = {
            "platform_supported": True,
            "logind": {"IdleAction": "suspend"},
            "sleep_conf": {"AllowSuspend": "yes"},
            "targets": {"suspend.target": "enabled"},
            "issues": [
                {"severity": "warning", "key": "logind.idle_action.suspend",
                 "message": "logind suspends after idle", "detail": "30min"}
            ],
            "sources": ["/etc/systemd/logind.conf"],
            "collected_at": "2026-05-09T12:00:00+00:00",
        }
        m = OsSleepReportResponse(**payload)
        assert m.issues[0].severity == "warning"
        assert m.issues[0].key == "logind.idle_action.suspend"

    def test_severity_must_be_known(self):
        bad = {
            "platform_supported": True,
            "issues": [{"severity": "purple", "key": "x", "message": "y"}],
        }
        with pytest.raises(ValidationError):
            OsSleepReportResponse(**bad)


class TestAlwaysAwake7DayCap:
    def test_until_at_7_days_minus_5min_accepted(self):
        v = datetime.now(timezone.utc) + timedelta(days=7) - timedelta(minutes=5)
        SleepConfigUpdate(always_awake_until=v)  # must not raise

    def test_until_8_days_in_future_rejected(self):
        v = datetime.now(timezone.utc) + timedelta(days=8)
        with pytest.raises(ValidationError) as exc:
            SleepConfigUpdate(always_awake_until=v)
        assert "7 days" in str(exc.value) or "7 Tagen" in str(exc.value)

    def test_until_naive_datetime_normalized_then_capped(self):
        # Naive value 8 days out — should be normalized to UTC and rejected.
        v = (datetime.utcnow() + timedelta(days=8)).replace(tzinfo=None)
        with pytest.raises(ValidationError):
            SleepConfigUpdate(always_awake_until=v)

    def test_until_in_past_still_rejected(self):
        v = datetime.now(timezone.utc) - timedelta(minutes=1)
        with pytest.raises(ValidationError):
            SleepConfigUpdate(always_awake_until=v)
