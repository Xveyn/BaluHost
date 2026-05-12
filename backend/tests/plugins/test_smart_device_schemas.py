"""Tests for SmartDevice Pydantic schemas — focusing on history import."""
from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from app.plugins.smart_device.schemas import (
    ImportHistoryRequest,
    ImportHistoryInterval,
    ImportHistoryConflictStrategy,
)


class TestImportHistoryRequest:
    def test_valid_hourly_request(self):
        req = ImportHistoryRequest(
            interval=ImportHistoryInterval.HOURLY,
            start_date="2026-04-01",
            end_date="2026-04-08",
            conflict_strategy=ImportHistoryConflictStrategy.LIVE_WINS,
        )
        assert req.interval == ImportHistoryInterval.HOURLY
        assert req.start_date.year == 2026

    def test_daily_requires_quarter_start(self):
        # April 1 is a quarter start — should pass
        ImportHistoryRequest(
            interval=ImportHistoryInterval.DAILY,
            start_date="2026-04-01",
            end_date="2026-06-30",
            conflict_strategy=ImportHistoryConflictStrategy.LIVE_WINS,
        )
        # April 15 is NOT a quarter start — must fail
        with pytest.raises(ValidationError):
            ImportHistoryRequest(
                interval=ImportHistoryInterval.DAILY,
                start_date="2026-04-15",
                end_date="2026-06-30",
                conflict_strategy=ImportHistoryConflictStrategy.LIVE_WINS,
            )

    def test_monthly_requires_year_start(self):
        ImportHistoryRequest(
            interval=ImportHistoryInterval.MONTHLY,
            start_date="2026-01-01",
            end_date="2026-12-31",
            conflict_strategy=ImportHistoryConflictStrategy.LIVE_WINS,
        )
        with pytest.raises(ValidationError):
            ImportHistoryRequest(
                interval=ImportHistoryInterval.MONTHLY,
                start_date="2026-03-01",
                end_date="2026-12-31",
                conflict_strategy=ImportHistoryConflictStrategy.LIVE_WINS,
            )

    def test_end_before_start_rejected(self):
        with pytest.raises(ValidationError):
            ImportHistoryRequest(
                interval=ImportHistoryInterval.HOURLY,
                start_date="2026-04-10",
                end_date="2026-04-01",
                conflict_strategy=ImportHistoryConflictStrategy.LIVE_WINS,
            )
