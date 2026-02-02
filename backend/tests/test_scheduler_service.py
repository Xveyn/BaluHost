"""
Tests for scheduler service.

Tests:
- Scheduler status and configuration
- Run-now functionality
- Toggle enable/disable
- Execution history
"""
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.services.scheduler_service import SchedulerService, _format_interval
from app.models.scheduler_history import (
    SchedulerExecution,
    SchedulerConfig,
    SchedulerStatus,
    TriggerType,
)


class TestFormatInterval:
    """Tests for interval formatting function."""

    def test_format_seconds(self):
        """Test formatting seconds."""
        assert _format_interval(30) == "Every 30s"
        assert _format_interval(45) == "Every 45s"

    def test_format_minutes(self):
        """Test formatting minutes."""
        assert _format_interval(60) == "Every minute"
        assert _format_interval(120) == "Every 2 min"
        assert _format_interval(300) == "Every 5 min"

    def test_format_hours(self):
        """Test formatting hours."""
        assert _format_interval(3600) == "Every hour"
        assert _format_interval(7200) == "Every 2h"
        assert _format_interval(21600) == "Every 6h"

    def test_format_days(self):
        """Test formatting days."""
        assert _format_interval(86400) == "Daily"
        assert _format_interval(172800) == "Every 2 days"
        assert _format_interval(604800) == "Every 7 days"


class TestSchedulerServiceInit:
    """Tests for SchedulerService initialization."""

    def test_init(self, db_session: Session):
        """Test service initialization."""
        service = SchedulerService(db_session)

        assert service.db is db_session


class TestGetAllSchedulers:
    """Tests for get_all_schedulers method."""

    def test_returns_scheduler_list_response(self, db_session: Session):
        """Test that method returns proper response type."""
        from app.schemas.scheduler import SchedulerListResponse

        service = SchedulerService(db_session)

        result = service.get_all_schedulers()

        assert isinstance(result, SchedulerListResponse)
        assert hasattr(result, 'schedulers')
        assert hasattr(result, 'total_running')
        assert hasattr(result, 'total_enabled')

    def test_contains_registered_schedulers(self, db_session: Session):
        """Test that result contains registered schedulers."""
        from app.schemas.scheduler import SCHEDULER_REGISTRY

        service = SchedulerService(db_session)

        result = service.get_all_schedulers()

        # Should have same number of schedulers as registry
        assert len(result.schedulers) == len(SCHEDULER_REGISTRY)


class TestGetScheduler:
    """Tests for get_scheduler method."""

    def test_get_existing_scheduler(self, db_session: Session):
        """Test getting an existing scheduler."""
        from app.schemas.scheduler import SCHEDULER_REGISTRY

        service = SchedulerService(db_session)

        # Get first scheduler from registry
        if SCHEDULER_REGISTRY:
            name = list(SCHEDULER_REGISTRY.keys())[0]
            result = service.get_scheduler(name)

            assert result is not None
            assert result.name == name

    def test_get_nonexistent_scheduler(self, db_session: Session):
        """Test getting a non-existent scheduler."""
        service = SchedulerService(db_session)

        result = service.get_scheduler("nonexistent_scheduler")

        assert result is None


class TestSchedulerStatusResponse:
    """Tests for scheduler status response structure."""

    def test_status_response_fields(self, db_session: Session):
        """Test that status response has all required fields."""
        from app.schemas.scheduler import SCHEDULER_REGISTRY

        service = SchedulerService(db_session)

        if SCHEDULER_REGISTRY:
            name = list(SCHEDULER_REGISTRY.keys())[0]
            result = service.get_scheduler(name)

            assert result is not None
            assert hasattr(result, 'name')
            assert hasattr(result, 'display_name')
            assert hasattr(result, 'description')
            assert hasattr(result, 'is_running')
            assert hasattr(result, 'is_enabled')
            assert hasattr(result, 'interval_seconds')
            assert hasattr(result, 'interval_display')


class TestCheckSchedulerRunning:
    """Tests for _check_scheduler_running method."""

    def test_returns_bool(self, db_session: Session):
        """Test that method returns boolean."""
        service = SchedulerService(db_session)

        result = service._check_scheduler_running("raid_scrub")

        assert isinstance(result, bool)

    def test_unknown_scheduler_returns_false(self, db_session: Session):
        """Test that unknown scheduler returns False."""
        service = SchedulerService(db_session)

        result = service._check_scheduler_running("unknown_scheduler")

        assert result is False


class TestCheckSchedulerEnabled:
    """Tests for _check_scheduler_enabled method."""

    def test_returns_bool(self, db_session: Session):
        """Test that method returns boolean."""
        service = SchedulerService(db_session)

        result = service._check_scheduler_enabled("sync_check")

        assert isinstance(result, bool)

    def test_sync_check_always_enabled(self, db_session: Session):
        """Test that sync_check is always enabled when running."""
        service = SchedulerService(db_session)

        result = service._check_scheduler_enabled("sync_check")

        assert result is True


class TestGetSchedulerInterval:
    """Tests for _get_scheduler_interval method."""

    def test_returns_int(self, db_session: Session):
        """Test that method returns integer."""
        from app.schemas.scheduler import SCHEDULER_REGISTRY

        service = SchedulerService(db_session)

        if SCHEDULER_REGISTRY:
            name = list(SCHEDULER_REGISTRY.keys())[0]
            info = SCHEDULER_REGISTRY[name]
            result = service._get_scheduler_interval(name, info)

            assert isinstance(result, int)
            assert result > 0

    def test_sync_check_interval(self, db_session: Session):
        """Test sync_check interval is 5 minutes."""
        from app.schemas.scheduler import SCHEDULER_REGISTRY

        service = SchedulerService(db_session)

        info = SCHEDULER_REGISTRY.get("sync_check", {})
        result = service._get_scheduler_interval("sync_check", info)

        assert result == 300  # 5 minutes


class TestSchedulerExecution:
    """Tests for execution history tracking."""

    def test_create_execution_record(self, db_session: Session):
        """Test creating an execution record."""
        execution = SchedulerExecution(
            scheduler_name="test_scheduler",
            started_at=datetime.now(timezone.utc),
            status=SchedulerStatus.COMPLETED,
            trigger_type=TriggerType.MANUAL,
            duration_ms=1500,
        )
        db_session.add(execution)
        db_session.commit()

        # Verify it was saved
        saved = db_session.query(SchedulerExecution).filter(
            SchedulerExecution.scheduler_name == "test_scheduler"
        ).first()

        assert saved is not None
        assert saved.status == SchedulerStatus.COMPLETED
        assert saved.duration_ms == 1500

    def test_execution_status_enum(self):
        """Test execution status enum values."""
        assert SchedulerStatus.RUNNING.value == "running"
        assert SchedulerStatus.COMPLETED.value == "completed"
        assert SchedulerStatus.FAILED.value == "failed"
        assert SchedulerStatus.CANCELLED.value == "cancelled"

    def test_trigger_type_enum(self):
        """Test trigger type enum values."""
        assert TriggerType.SCHEDULED.value == "scheduled"
        assert TriggerType.MANUAL.value == "manual"


class TestSchedulerConfig:
    """Tests for scheduler configuration."""

    def test_create_config(self, db_session: Session):
        """Test creating a scheduler config."""
        config = SchedulerConfig(
            scheduler_name="test_scheduler",
            is_enabled=True,
            interval_seconds=3600,
        )
        db_session.add(config)
        db_session.commit()

        # Verify it was saved
        saved = db_session.query(SchedulerConfig).filter(
            SchedulerConfig.scheduler_name == "test_scheduler"
        ).first()

        assert saved is not None
        assert saved.is_enabled is True
        assert saved.interval_seconds == 3600

    def test_config_defaults(self, db_session: Session):
        """Test config default values."""
        config = SchedulerConfig(
            scheduler_name="default_test",
            interval_seconds=300,  # Required field
        )
        db_session.add(config)
        db_session.commit()

        saved = db_session.query(SchedulerConfig).filter(
            SchedulerConfig.scheduler_name == "default_test"
        ).first()

        # is_enabled defaults to True
        assert saved.is_enabled is True
