"""
Tests for SyncSchedulerService.

Tests:
- Schedule creation (with and without auto_vpn)
- Schedule update (fields + auto_vpn)
- Schedule enable/disable
- Schedule listing (returns all, including disabled)
- Next run calculation for daily/weekly/monthly/on_change
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.models.sync_progress import SyncSchedule
from app.models.user import User
from app.services.sync.scheduler import SyncSchedulerService


@pytest.fixture
def user(db_session: Session) -> User:
    """Create a test user for sync schedule tests."""
    from app.schemas.user import UserCreate
    from app.services import users as user_service

    return user_service.create_user(
        UserCreate(
            username="syncuser",
            email="sync@test.com",
            password="Syncpass123!",
            role="user",
        ),
        db=db_session,
    )


@pytest.fixture
def scheduler(db_session: Session) -> SyncSchedulerService:
    """Create a SyncSchedulerService instance."""
    return SyncSchedulerService(db_session)


class TestCreateSchedule:
    """Tests for schedule creation."""

    def test_create_daily_schedule(self, scheduler: SyncSchedulerService, user: User):
        result = scheduler.create_schedule(
            user_id=user.id,
            device_id="device-001",
            schedule_type="daily",
            time_of_day="03:00",
        )

        assert result["schedule_id"] is not None
        assert result["device_id"] == "device-001"
        assert result["schedule_type"] == "daily"
        assert result["time_of_day"] == "03:00"
        assert result["enabled"] is True
        assert result["auto_vpn"] is False
        assert result["next_run_at"] is not None

    def test_create_weekly_schedule(self, scheduler: SyncSchedulerService, user: User):
        result = scheduler.create_schedule(
            user_id=user.id,
            device_id="device-001",
            schedule_type="weekly",
            time_of_day="22:00",
            day_of_week=3,  # Wednesday
        )

        assert result["schedule_type"] == "weekly"
        assert result["day_of_week"] == 3
        assert result["next_run_at"] is not None

    def test_create_monthly_schedule(self, scheduler: SyncSchedulerService, user: User):
        result = scheduler.create_schedule(
            user_id=user.id,
            device_id="device-001",
            schedule_type="monthly",
            time_of_day="01:00",
            day_of_month=15,
        )

        assert result["schedule_type"] == "monthly"
        assert result["day_of_month"] == 15
        assert result["next_run_at"] is not None

    def test_create_on_change_schedule(self, scheduler: SyncSchedulerService, user: User):
        result = scheduler.create_schedule(
            user_id=user.id,
            device_id="device-001",
            schedule_type="on_change",
        )

        assert result["schedule_type"] == "on_change"
        assert result["next_run_at"] is None

    def test_create_with_auto_vpn(self, scheduler: SyncSchedulerService, user: User):
        result = scheduler.create_schedule(
            user_id=user.id,
            device_id="device-001",
            schedule_type="daily",
            time_of_day="04:00",
            auto_vpn=True,
        )

        assert result["auto_vpn"] is True

    def test_create_with_sync_settings(self, scheduler: SyncSchedulerService, user: User):
        result = scheduler.create_schedule(
            user_id=user.id,
            device_id="device-001",
            schedule_type="daily",
            sync_deletions=False,
            resolve_conflicts="keep_local",
        )

        assert result["sync_deletions"] is False
        assert result["resolve_conflicts"] == "keep_local"

    def test_create_defaults_time_to_0200(self, scheduler: SyncSchedulerService, user: User):
        result = scheduler.create_schedule(
            user_id=user.id,
            device_id="device-001",
            schedule_type="daily",
        )

        assert result["time_of_day"] == "02:00"

    def test_create_multiple_schedules(self, scheduler: SyncSchedulerService, user: User):
        s1 = scheduler.create_schedule(
            user_id=user.id, device_id="device-001", schedule_type="daily"
        )
        s2 = scheduler.create_schedule(
            user_id=user.id, device_id="device-002", schedule_type="weekly", day_of_week=0
        )

        assert s1["schedule_id"] != s2["schedule_id"]


class TestGetSchedules:
    """Tests for listing schedules."""

    def test_empty_list(self, scheduler: SyncSchedulerService, user: User):
        result = scheduler.get_schedules(user.id)
        assert result == []

    def test_returns_all_schedules_including_disabled(
        self, scheduler: SyncSchedulerService, user: User, db_session: Session
    ):
        scheduler.create_schedule(
            user_id=user.id, device_id="d1", schedule_type="daily"
        )
        s2 = scheduler.create_schedule(
            user_id=user.id, device_id="d2", schedule_type="weekly", day_of_week=1
        )
        scheduler.disable_schedule(s2["schedule_id"], user.id)

        result = scheduler.get_schedules(user.id)
        assert len(result) == 2

        enabled_states = {s["device_id"]: s["enabled"] for s in result}
        assert enabled_states["d1"] is True
        assert enabled_states["d2"] is False

    def test_returns_auto_vpn_field(self, scheduler: SyncSchedulerService, user: User):
        scheduler.create_schedule(
            user_id=user.id, device_id="d1", schedule_type="daily", auto_vpn=True
        )
        scheduler.create_schedule(
            user_id=user.id, device_id="d2", schedule_type="daily", auto_vpn=False
        )

        result = scheduler.get_schedules(user.id)
        vpn_map = {s["device_id"]: s["auto_vpn"] for s in result}
        assert vpn_map["d1"] is True
        assert vpn_map["d2"] is False

    def test_user_isolation(
        self, scheduler: SyncSchedulerService, user: User, db_session: Session
    ):
        """Schedules from one user are not visible to another."""
        from app.schemas.user import UserCreate
        from app.services import users as user_service

        other = user_service.create_user(
            UserCreate(
                username="otheruser",
                email="other@test.com",
                password="Otherpass123!",
                role="user",
            ),
            db=db_session,
        )

        scheduler.create_schedule(
            user_id=user.id, device_id="d1", schedule_type="daily"
        )
        scheduler.create_schedule(
            user_id=other.id, device_id="d2", schedule_type="daily"
        )

        user_schedules = scheduler.get_schedules(user.id)
        other_schedules = scheduler.get_schedules(other.id)

        assert len(user_schedules) == 1
        assert user_schedules[0]["device_id"] == "d1"
        assert len(other_schedules) == 1
        assert other_schedules[0]["device_id"] == "d2"

    def test_response_contains_all_fields(self, scheduler: SyncSchedulerService, user: User):
        scheduler.create_schedule(
            user_id=user.id,
            device_id="d1",
            schedule_type="daily",
            time_of_day="05:00",
            sync_deletions=False,
            resolve_conflicts="keep_server",
            auto_vpn=True,
        )

        result = scheduler.get_schedules(user.id)
        assert len(result) == 1
        s = result[0]

        expected_keys = {
            "schedule_id", "device_id", "device_name", "schedule_type", "time_of_day",
            "day_of_week", "day_of_month", "next_run_at", "last_run_at",
            "enabled", "sync_deletions", "resolve_conflicts", "auto_vpn",
        }
        assert set(s.keys()) == expected_keys


class TestDisableSchedule:
    """Tests for disabling schedules."""

    def test_disable_existing(self, scheduler: SyncSchedulerService, user: User):
        created = scheduler.create_schedule(
            user_id=user.id, device_id="d1", schedule_type="daily"
        )

        result = scheduler.disable_schedule(created["schedule_id"], user.id)
        assert result is True

        schedules = scheduler.get_schedules(user.id)
        assert schedules[0]["enabled"] is False

    def test_disable_nonexistent(self, scheduler: SyncSchedulerService, user: User):
        result = scheduler.disable_schedule(9999, user.id)
        assert result is False

    def test_disable_wrong_user(
        self, scheduler: SyncSchedulerService, user: User, db_session: Session
    ):
        from app.schemas.user import UserCreate
        from app.services import users as user_service

        other = user_service.create_user(
            UserCreate(
                username="attacker",
                email="attacker@test.com",
                password="Attackpass123!",
                role="user",
            ),
            db=db_session,
        )

        created = scheduler.create_schedule(
            user_id=user.id, device_id="d1", schedule_type="daily"
        )

        result = scheduler.disable_schedule(created["schedule_id"], other.id)
        assert result is False


class TestEnableSchedule:
    """Tests for enabling schedules."""

    def test_enable_disabled_schedule(self, scheduler: SyncSchedulerService, user: User):
        created = scheduler.create_schedule(
            user_id=user.id, device_id="d1", schedule_type="daily"
        )
        scheduler.disable_schedule(created["schedule_id"], user.id)

        result = scheduler.enable_schedule(created["schedule_id"], user.id)
        assert result is True

        schedules = scheduler.get_schedules(user.id)
        assert schedules[0]["enabled"] is True
        # Re-enabling should recalculate next_run_at
        assert schedules[0]["next_run_at"] is not None

    def test_enable_nonexistent(self, scheduler: SyncSchedulerService, user: User):
        result = scheduler.enable_schedule(9999, user.id)
        assert result is False

    def test_enable_wrong_user(
        self, scheduler: SyncSchedulerService, user: User, db_session: Session
    ):
        from app.schemas.user import UserCreate
        from app.services import users as user_service

        other = user_service.create_user(
            UserCreate(
                username="attacker2",
                email="attacker2@test.com",
                password="Attackpass123!",
                role="user",
            ),
            db=db_session,
        )

        created = scheduler.create_schedule(
            user_id=user.id, device_id="d1", schedule_type="daily"
        )
        scheduler.disable_schedule(created["schedule_id"], user.id)

        result = scheduler.enable_schedule(created["schedule_id"], other.id)
        assert result is False


class TestUpdateSchedule:
    """Tests for updating schedules."""

    def test_update_time(self, scheduler: SyncSchedulerService, user: User):
        created = scheduler.create_schedule(
            user_id=user.id, device_id="d1", schedule_type="daily", time_of_day="02:00"
        )

        result = scheduler.update_schedule(
            schedule_id=created["schedule_id"],
            user_id=user.id,
            time_of_day="06:00",
        )

        assert result is not None
        assert result["time_of_day"] == "06:00"

    def test_update_auto_vpn(self, scheduler: SyncSchedulerService, user: User):
        created = scheduler.create_schedule(
            user_id=user.id, device_id="d1", schedule_type="daily", auto_vpn=False
        )

        result = scheduler.update_schedule(
            schedule_id=created["schedule_id"],
            user_id=user.id,
            auto_vpn=True,
        )

        assert result is not None
        assert result["auto_vpn"] is True

    def test_update_schedule_type(self, scheduler: SyncSchedulerService, user: User):
        created = scheduler.create_schedule(
            user_id=user.id, device_id="d1", schedule_type="daily"
        )

        result = scheduler.update_schedule(
            schedule_id=created["schedule_id"],
            user_id=user.id,
            schedule_type="weekly",
            day_of_week=5,
        )

        assert result is not None
        assert result["schedule_type"] == "weekly"

    def test_update_nonexistent(self, scheduler: SyncSchedulerService, user: User):
        result = scheduler.update_schedule(
            schedule_id=9999,
            user_id=user.id,
            time_of_day="06:00",
        )
        assert result is None

    def test_update_ignores_none_values(self, scheduler: SyncSchedulerService, user: User):
        created = scheduler.create_schedule(
            user_id=user.id,
            device_id="d1",
            schedule_type="daily",
            time_of_day="03:00",
            auto_vpn=True,
        )

        result = scheduler.update_schedule(
            schedule_id=created["schedule_id"],
            user_id=user.id,
            time_of_day=None,
            auto_vpn=None,
        )

        assert result is not None
        # Original values preserved
        assert result["time_of_day"] == "03:00"
        assert result["auto_vpn"] is True


class TestNextRunCalculation:
    """Tests for next_run_at calculation."""

    @staticmethod
    def _parse_next_run(iso_str: str) -> datetime:
        """Parse next_run_at ISO string, handling naive datetimes from SQLite."""
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    def test_daily_next_run_is_future(self, scheduler: SyncSchedulerService, user: User):
        result = scheduler.create_schedule(
            user_id=user.id, device_id="d1", schedule_type="daily", time_of_day="23:59"
        )

        next_run = self._parse_next_run(result["next_run_at"])
        assert next_run > datetime.now(timezone.utc) - timedelta(minutes=1)

    def test_weekly_next_run_is_future(self, scheduler: SyncSchedulerService, user: User):
        result = scheduler.create_schedule(
            user_id=user.id, device_id="d1", schedule_type="weekly",
            time_of_day="12:00", day_of_week=0,
        )

        next_run = self._parse_next_run(result["next_run_at"])
        assert next_run > datetime.now(timezone.utc) - timedelta(minutes=1)

    def test_monthly_next_run_is_future(self, scheduler: SyncSchedulerService, user: User):
        result = scheduler.create_schedule(
            user_id=user.id, device_id="d1", schedule_type="monthly",
            time_of_day="12:00", day_of_month=1,
        )

        next_run = self._parse_next_run(result["next_run_at"])
        assert next_run > datetime.now(timezone.utc) - timedelta(minutes=1)

    def test_on_change_has_no_next_run(self, scheduler: SyncSchedulerService, user: User):
        result = scheduler.create_schedule(
            user_id=user.id, device_id="d1", schedule_type="on_change"
        )

        assert result["next_run_at"] is None
