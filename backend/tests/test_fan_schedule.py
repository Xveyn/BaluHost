"""
Tests for fan schedule (time-based fan curves) feature.

Tests cover:
- _time_in_window() helper: normal windows, overnight windows, edge cases
- _resolve_active_curve(): no match, priority ordering, disabled entries
- API endpoints: CRUD operations for schedule entries
"""
import json
import pytest
from pydantic import ValidationError
from unittest.mock import patch, MagicMock
from datetime import datetime

from app.models.fans import FanConfig, FanScheduleEntry
from app.schemas.fans import FanMode, FanCurvePoint
from app.services.fan_control import FanControlService


# ============================================================================
# Unit Tests: _time_in_window
# ============================================================================

class TestTimeInWindow:
    """Test the static _time_in_window method."""

    def test_normal_window_inside(self):
        """08:00-18:00, current 12:00 -> True"""
        assert FanControlService._time_in_window(720, 480, 1080) is True

    def test_normal_window_at_start(self):
        """08:00-18:00, current 08:00 -> True"""
        assert FanControlService._time_in_window(480, 480, 1080) is True

    def test_normal_window_before_end(self):
        """08:00-18:00, current 17:59 -> True"""
        assert FanControlService._time_in_window(1079, 480, 1080) is True

    def test_normal_window_at_end(self):
        """08:00-18:00, current 18:00 -> False (end is exclusive)"""
        assert FanControlService._time_in_window(1080, 480, 1080) is False

    def test_normal_window_before_start(self):
        """08:00-18:00, current 07:00 -> False"""
        assert FanControlService._time_in_window(420, 480, 1080) is False

    def test_normal_window_after_end(self):
        """08:00-18:00, current 20:00 -> False"""
        assert FanControlService._time_in_window(1200, 480, 1080) is False

    def test_overnight_window_evening(self):
        """22:00-06:00, current 23:00 -> True"""
        assert FanControlService._time_in_window(1380, 1320, 360) is True

    def test_overnight_window_morning(self):
        """22:00-06:00, current 03:00 -> True"""
        assert FanControlService._time_in_window(180, 1320, 360) is True

    def test_overnight_window_at_start(self):
        """22:00-06:00, current 22:00 -> True"""
        assert FanControlService._time_in_window(1320, 1320, 360) is True

    def test_overnight_window_at_end(self):
        """22:00-06:00, current 06:00 -> False (end is exclusive)"""
        assert FanControlService._time_in_window(360, 1320, 360) is False

    def test_overnight_window_daytime(self):
        """22:00-06:00, current 12:00 -> False"""
        assert FanControlService._time_in_window(720, 1320, 360) is False

    def test_midnight_boundary(self):
        """23:00-01:00, current 00:00 -> True"""
        assert FanControlService._time_in_window(0, 1380, 60) is True

    def test_midnight_boundary_outside(self):
        """23:00-01:00, current 02:00 -> False"""
        assert FanControlService._time_in_window(120, 1380, 60) is False

    def test_full_day_window(self):
        """00:00-00:00 is treated as start==end, which means 0 <= x < 0 -> False"""
        assert FanControlService._time_in_window(720, 0, 0) is False


class TestParseTimeToMinutes:
    """Test time string parsing."""

    def test_midnight(self):
        assert FanControlService._parse_time_to_minutes("00:00") == 0

    def test_noon(self):
        assert FanControlService._parse_time_to_minutes("12:00") == 720

    def test_evening(self):
        assert FanControlService._parse_time_to_minutes("22:30") == 1350

    def test_end_of_day(self):
        assert FanControlService._parse_time_to_minutes("23:59") == 1439


# ============================================================================
# Unit Tests: _resolve_active_curve
# ============================================================================

class TestResolveActiveCurve:
    """Test curve resolution from schedule entries."""

    def _create_service_with_mock_db(self):
        """Create a FanControlService with mocked dependencies."""
        # Reset singleton
        FanControlService._instance = None
        config = MagicMock()
        config.fan_control_enabled = False
        config.is_dev_mode = True
        config.fan_force_dev_backend = True
        service = FanControlService(config, MagicMock())
        return service

    def test_no_entries_returns_default(self, db_session):
        """No schedule entries -> returns default curve."""
        service = self._create_service_with_mock_db()
        default_curve = json.dumps([{"temp": 35, "pwm": 30}, {"temp": 85, "pwm": 100}])

        curve, entry = service._resolve_active_curve("test_fan", default_curve, db_session)

        assert entry is None
        assert len(curve) == 2
        assert curve[0]["temp"] == 35

        # Cleanup singleton
        FanControlService._instance = None

    def test_matching_entry_returns_its_curve(self, db_session):
        """Entry matching current time returns its curve."""
        service = self._create_service_with_mock_db()

        # Create an entry that covers the entire day (00:00-23:59 normal window)
        entry = FanScheduleEntry(
            fan_id="test_fan",
            name="All Day",
            start_time="00:00",
            end_time="23:59",
            curve_json=json.dumps([{"temp": 40, "pwm": 25}, {"temp": 80, "pwm": 60}]),
            priority=0,
            is_enabled=True,
        )
        db_session.add(entry)
        db_session.commit()

        default_curve = json.dumps([{"temp": 35, "pwm": 30}, {"temp": 85, "pwm": 100}])
        curve, active = service._resolve_active_curve("test_fan", default_curve, db_session)

        assert active is not None
        assert active.name == "All Day"
        assert len(curve) == 2
        assert curve[0]["pwm"] == 25

        FanControlService._instance = None

    def test_disabled_entry_is_skipped(self, db_session):
        """Disabled entries are not considered."""
        service = self._create_service_with_mock_db()

        entry = FanScheduleEntry(
            fan_id="test_fan",
            name="Disabled Entry",
            start_time="00:00",
            end_time="23:59",
            curve_json=json.dumps([{"temp": 40, "pwm": 25}, {"temp": 80, "pwm": 60}]),
            priority=0,
            is_enabled=False,
        )
        db_session.add(entry)
        db_session.commit()

        default_curve = json.dumps([{"temp": 35, "pwm": 30}, {"temp": 85, "pwm": 100}])
        curve, active = service._resolve_active_curve("test_fan", default_curve, db_session)

        assert active is None
        assert curve[0]["temp"] == 35  # Default curve

        FanControlService._instance = None

    def test_priority_ordering(self, db_session):
        """Lower priority number wins when multiple entries match."""
        service = self._create_service_with_mock_db()

        low_prio = FanScheduleEntry(
            fan_id="test_fan",
            name="Low Priority",
            start_time="00:00",
            end_time="23:59",
            curve_json=json.dumps([{"temp": 40, "pwm": 50}, {"temp": 80, "pwm": 90}]),
            priority=10,
            is_enabled=True,
        )
        high_prio = FanScheduleEntry(
            fan_id="test_fan",
            name="High Priority",
            start_time="00:00",
            end_time="23:59",
            curve_json=json.dumps([{"temp": 40, "pwm": 20}, {"temp": 80, "pwm": 40}]),
            priority=0,
            is_enabled=True,
        )
        db_session.add_all([low_prio, high_prio])
        db_session.commit()

        default_curve = json.dumps([{"temp": 35, "pwm": 30}, {"temp": 85, "pwm": 100}])
        curve, active = service._resolve_active_curve("test_fan", default_curve, db_session)

        assert active is not None
        assert active.name == "High Priority"
        assert curve[0]["pwm"] == 20

        FanControlService._instance = None

    def test_different_fan_id_not_matched(self, db_session):
        """Entries for a different fan_id are not returned."""
        service = self._create_service_with_mock_db()

        entry = FanScheduleEntry(
            fan_id="other_fan",
            name="Other Fan Entry",
            start_time="00:00",
            end_time="23:59",
            curve_json=json.dumps([{"temp": 40, "pwm": 25}, {"temp": 80, "pwm": 60}]),
            priority=0,
            is_enabled=True,
        )
        db_session.add(entry)
        db_session.commit()

        default_curve = json.dumps([{"temp": 35, "pwm": 30}, {"temp": 85, "pwm": 100}])
        curve, active = service._resolve_active_curve("test_fan", default_curve, db_session)

        assert active is None

        FanControlService._instance = None


# ============================================================================
# Integration Tests: CRUD via Service (using test DB session)
# ============================================================================

class TestFanScheduleService:
    """Test fan schedule CRUD operations via the service layer with test DB."""

    def _create_service(self, db_session):
        """Create a FanControlService wired to the test DB session."""
        FanControlService._instance = None
        config = MagicMock()
        config.fan_control_enabled = False
        config.is_dev_mode = True
        config.fan_force_dev_backend = True
        service = FanControlService(config, lambda: db_session)
        return service

    @pytest.mark.asyncio
    async def test_create_and_list_entries(self, db_session):
        """Creating entries and listing them."""
        service = self._create_service(db_session)
        try:
            entry = await service.create_schedule_entry(
                fan_id="test_fan",
                name="Night Mode",
                start_time="22:00",
                end_time="06:00",
                curve_points=[FanCurvePoint(temp=40, pwm=30), FanCurvePoint(temp=80, pwm=100)],
                priority=0,
            )
            assert entry is not None
            assert entry.name == "Night Mode"

            entries = await service.get_schedule_entries("test_fan")
            assert len(entries) == 1
            assert entries[0].name == "Night Mode"
        finally:
            FanControlService._instance = None

    @pytest.mark.asyncio
    async def test_update_entry(self, db_session):
        """Updating an existing entry."""
        service = self._create_service(db_session)
        try:
            entry = await service.create_schedule_entry(
                fan_id="test_fan",
                name="Original",
                start_time="08:00",
                end_time="18:00",
                curve_points=[FanCurvePoint(temp=40, pwm=30), FanCurvePoint(temp=80, pwm=100)],
            )
            assert entry is not None

            updated = await service.update_schedule_entry(
                "test_fan", entry.id, name="Updated", start_time="09:00"
            )
            assert updated is not None
            assert updated.name == "Updated"
            assert updated.start_time == "09:00"
            assert updated.end_time == "18:00"  # Unchanged
        finally:
            FanControlService._instance = None

    @pytest.mark.asyncio
    async def test_delete_entry(self, db_session):
        """Deleting an entry."""
        service = self._create_service(db_session)
        try:
            entry = await service.create_schedule_entry(
                fan_id="test_fan",
                name="To Delete",
                start_time="08:00",
                end_time="18:00",
                curve_points=[FanCurvePoint(temp=40, pwm=30), FanCurvePoint(temp=80, pwm=100)],
            )
            assert entry is not None

            success = await service.delete_schedule_entry("test_fan", entry.id)
            assert success is True

            entries = await service.get_schedule_entries("test_fan")
            assert len(entries) == 0
        finally:
            FanControlService._instance = None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_entry(self, db_session):
        """Deleting a non-existent entry returns False."""
        service = self._create_service(db_session)
        try:
            success = await service.delete_schedule_entry("test_fan", 99999)
            assert success is False
        finally:
            FanControlService._instance = None

    @pytest.mark.asyncio
    async def test_max_entries_limit(self, db_session):
        """Cannot create more than 8 entries per fan."""
        service = self._create_service(db_session)
        try:
            for i in range(8):
                entry = await service.create_schedule_entry(
                    fan_id="test_fan",
                    name=f"Entry {i}",
                    start_time=f"{i:02d}:00",
                    end_time=f"{i:02d}:30",
                    curve_points=[FanCurvePoint(temp=40, pwm=30), FanCurvePoint(temp=80, pwm=100)],
                )
                assert entry is not None

            # 9th should return None
            entry = await service.create_schedule_entry(
                fan_id="test_fan",
                name="Too Many",
                start_time="08:00",
                end_time="09:00",
                curve_points=[FanCurvePoint(temp=40, pwm=30), FanCurvePoint(temp=80, pwm=100)],
            )
            assert entry is None
        finally:
            FanControlService._instance = None

    @pytest.mark.asyncio
    async def test_toggle_entry(self, db_session):
        """Toggling is_enabled on an entry."""
        service = self._create_service(db_session)
        try:
            entry = await service.create_schedule_entry(
                fan_id="test_fan",
                name="Toggleable",
                start_time="08:00",
                end_time="18:00",
                curve_points=[FanCurvePoint(temp=40, pwm=30), FanCurvePoint(temp=80, pwm=100)],
                is_enabled=True,
            )
            assert entry is not None
            assert entry.is_enabled is True

            updated = await service.update_schedule_entry(
                "test_fan", entry.id, is_enabled=False
            )
            assert updated is not None
            assert updated.is_enabled is False
        finally:
            FanControlService._instance = None

    @pytest.mark.asyncio
    async def test_wrong_fan_id_update_returns_none(self, db_session):
        """Updating with wrong fan_id returns None."""
        service = self._create_service(db_session)
        try:
            entry = await service.create_schedule_entry(
                fan_id="test_fan",
                name="Test",
                start_time="08:00",
                end_time="18:00",
                curve_points=[FanCurvePoint(temp=40, pwm=30), FanCurvePoint(temp=80, pwm=100)],
            )
            assert entry is not None

            result = await service.update_schedule_entry("wrong_fan", entry.id, name="Hacked")
            assert result is None
        finally:
            FanControlService._instance = None


# ============================================================================
# Schema Validation Tests
# ============================================================================

class TestFanScheduleSchemas:
    """Test Pydantic schema validation for schedule entries."""

    def test_valid_create_request(self):
        """Valid creation request passes validation."""
        from app.schemas.fans import CreateFanScheduleEntryRequest
        req = CreateFanScheduleEntryRequest(
            name="Night Mode",
            start_time="22:00",
            end_time="06:00",
            curve_points=[
                FanCurvePoint(temp=40, pwm=30),
                FanCurvePoint(temp=80, pwm=100),
            ],
            priority=0,
        )
        assert req.name == "Night Mode"
        assert req.start_time == "22:00"

    def test_invalid_time_rejected(self):
        """Invalid time format (25:00) is rejected."""
        from app.schemas.fans import CreateFanScheduleEntryRequest
        with pytest.raises(ValidationError):
            CreateFanScheduleEntryRequest(
                name="Bad",
                start_time="25:00",
                end_time="06:00",
                curve_points=[
                    FanCurvePoint(temp=40, pwm=30),
                    FanCurvePoint(temp=80, pwm=100),
                ],
            )

    def test_insufficient_curve_points_rejected(self):
        """Fewer than 2 curve points is rejected."""
        from app.schemas.fans import CreateFanScheduleEntryRequest
        with pytest.raises(ValidationError):
            CreateFanScheduleEntryRequest(
                name="Bad",
                start_time="08:00",
                end_time="18:00",
                curve_points=[FanCurvePoint(temp=40, pwm=30)],
            )

    def test_scheduled_mode_in_enum(self):
        """SCHEDULED is a valid FanMode value."""
        assert FanMode.SCHEDULED.value == "scheduled"
        assert FanMode("scheduled") == FanMode.SCHEDULED

    def test_curve_points_sorted_by_temp(self):
        """Curve points are auto-sorted by temperature."""
        from app.schemas.fans import CreateFanScheduleEntryRequest
        req = CreateFanScheduleEntryRequest(
            name="Test",
            start_time="08:00",
            end_time="18:00",
            curve_points=[
                FanCurvePoint(temp=80, pwm=100),
                FanCurvePoint(temp=40, pwm=30),
            ],
        )
        assert req.curve_points[0].temp == 40
        assert req.curve_points[1].temp == 80
