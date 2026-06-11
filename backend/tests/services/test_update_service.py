"""
Tests for update service.

Tests:
- Version parsing and conversion
- DevUpdateBackend simulation
- Update checking and configuration
- Update history tracking
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from sqlalchemy.orm import Session

from app.services.update import (
    parse_version,
    version_to_string,
    version_sort_key,
    DevUpdateBackend,
    UpdateService,
    get_update_backend,
)
from app.models.update_history import (
    UpdateHistory,
    UpdateConfig,
    UpdateStatus,
    UpdateChannel,
)


class TestVersionParsing:
    """Tests for version parsing functions."""

    def test_parse_simple_version(self):
        """Test parsing simple version tag."""
        result = parse_version("1.5.0")
        assert result == (1, 5, 0, "")

    def test_parse_version_with_v_prefix(self):
        """Test parsing version with 'v' prefix."""
        result = parse_version("v1.5.0")
        assert result == (1, 5, 0, "")

    def test_parse_version_with_prerelease(self):
        """Test parsing version with prerelease suffix."""
        result = parse_version("1.6.0-beta")
        assert result == (1, 6, 0, "beta")

    def test_parse_version_with_prerelease_and_prefix(self):
        """Test parsing version with 'v' prefix and prerelease."""
        result = parse_version("v1.6.0-rc1")
        assert result == (1, 6, 0, "rc1")

    def test_parse_partial_version(self):
        """Test parsing partial version number."""
        result = parse_version("1.5")
        assert result == (1, 5, 0, "")

    def test_parse_major_only(self):
        """Test parsing major version only."""
        result = parse_version("2")
        assert result == (2, 0, 0, "")

    def test_version_comparison(self):
        """Major/minor/patch ordering via version_sort_key."""
        assert version_sort_key("1.6.0") > version_sort_key("1.5.0")


class TestVersionSortKey:
    """SemVer-correct ordering (issue #120) — parse_version tuples are NOT ordering-safe."""

    def test_stable_ranks_above_its_prerelease(self):
        assert version_sort_key("1.33.1") > version_sort_key("1.33.1-pre.3")

    def test_numeric_prerelease_counters_sort_numerically(self):
        assert version_sort_key("1.33.1-pre.10") > version_sort_key("1.33.1-pre.2")

    def test_alphanumeric_identifiers_compare_lexically(self):
        # "pre" < "rc" lexically
        assert version_sort_key("1.33.1-pre.2") < version_sort_key("1.33.1-rc.1")

    def test_numeric_identifier_ranks_below_alphanumeric(self):
        # SemVer: numeric identifiers always have lower precedence
        assert version_sort_key("1.0.0-1") < version_sort_key("1.0.0-alpha")

    def test_fewer_identifiers_rank_lower(self):
        # SemVer: 1.0.0-alpha < 1.0.0-alpha.1
        assert version_sort_key("1.0.0-alpha") < version_sort_key("1.0.0-alpha.1")

    def test_equal_stables_and_v_prefix(self):
        assert version_sort_key("v1.36.0") == version_sort_key("1.36.0")

    def test_tolerates_non_numeric_header(self):
        # parity with parse_version's CHANGELOG "[Unreleased]" tolerance
        assert version_sort_key("Unreleased") == version_sort_key("0.0.0")

    def test_exotic_digit_identifier_does_not_crash(self):
        # "²".isdigit() is True but int("²") raises — isdecimal() routes it
        # to the alphanumeric branch instead of crashing.
        assert version_sort_key("1.0.0-pre.²") < version_sort_key("1.0.0")

    def test_list_sort_end_to_end(self):
        tags = ["v1.36.1-pre.2", "v1.36.1-pre.10", "v1.36.1", "v1.36.0", "v1.36.1-pre.9"]
        ordered = sorted(tags, key=version_sort_key)
        assert ordered == ["v1.36.0", "v1.36.1-pre.2", "v1.36.1-pre.9", "v1.36.1-pre.10", "v1.36.1"]


class TestVersionToString:
    """Tests for version to string conversion."""

    def test_simple_version(self):
        """Test converting simple version tuple to string."""
        result = version_to_string((1, 5, 0, ""))
        assert result == "1.5.0"

    def test_version_with_prerelease(self):
        """Test converting version with prerelease to string."""
        result = version_to_string((1, 6, 0, "beta"))
        assert result == "1.6.0-beta"

    def test_roundtrip(self):
        """Test that parse and convert are inverse operations."""
        original = "1.5.3"
        parsed = parse_version(original)
        result = version_to_string(parsed)
        assert result == original

    def test_roundtrip_with_prerelease(self):
        """Test roundtrip with prerelease version."""
        original = "2.0.0-alpha"
        parsed = parse_version(original)
        result = version_to_string(parsed)
        assert result == original


class TestDevUpdateBackend:
    """Tests for DevUpdateBackend simulation."""

    @pytest.fixture
    def backend(self):
        """Create a DevUpdateBackend instance."""
        return DevUpdateBackend()

    @pytest.mark.asyncio
    async def test_get_current_version(self, backend):
        """Test getting current version."""
        version = await backend.get_current_version()

        assert version is not None
        assert version.version == version_to_string(backend._simulated_version)
        assert version.commit is not None
        # Commit hash length depends on backend implementation
        assert len(version.commit) >= 7
        assert version.commit_short == version.commit[:7]

    @pytest.mark.asyncio
    async def test_check_for_updates_stable(self, backend):
        """Test checking for updates on stable channel."""
        available, latest, changelog = await backend.check_for_updates("stable")

        assert available is True
        assert latest is not None
        assert latest.version == version_to_string(backend._latest_version)
        assert len(changelog) >= 1
        assert changelog[0].is_prerelease is False

    @pytest.mark.asyncio
    async def test_check_for_updates_unstable(self, backend):
        """Test checking for updates on unstable channel."""
        available, latest, changelog = await backend.check_for_updates("unstable")

        assert available is True
        assert latest is not None
        # Beta version is next minor after latest
        major, minor, _, _ = backend._latest_version
        assert latest.version == f"{major}.{minor + 1}.0-beta"
        # Unstable channel includes both prerelease and stable releases
        assert len(changelog) >= 1
        assert any(entry.is_prerelease for entry in changelog)

    @pytest.mark.asyncio
    async def test_fetch_updates(self, backend):
        """Test fetching updates simulation."""
        progress_calls = []

        def callback(progress, step):
            progress_calls.append((progress, step))

        result = await backend.fetch_updates(callback=callback)

        assert result is True
        assert len(progress_calls) > 0
        assert progress_calls[-1][0] == 100

    @pytest.mark.asyncio
    async def test_apply_updates(self, backend):
        """Test applying updates simulation."""
        target_commit = "newcommit123456789abcdef1234567890ab"
        progress_calls = []

        def callback(progress, step):
            progress_calls.append((progress, step))

        success, error = await backend.apply_updates(target_commit, callback=callback)

        assert success is True
        assert error is None
        assert len(progress_calls) > 0

    @pytest.mark.asyncio
    async def test_install_dependencies(self, backend):
        """Test installing dependencies simulation."""
        success, error = await backend.install_dependencies()

        assert success is True
        assert error is None

    @pytest.mark.asyncio
    async def test_run_migrations(self, backend):
        """Test running migrations simulation."""
        success, error = await backend.run_migrations()

        assert success is True
        assert error is None

    @pytest.mark.asyncio
    async def test_restart_services(self, backend):
        """Test service restart simulation."""
        success, error = await backend.restart_services()

        assert success is True
        assert error is None

    @pytest.mark.asyncio
    async def test_rollback(self, backend):
        """Test rollback simulation."""
        commit = "oldcommit123456789abcdef1234567890ab"
        success, error = await backend.rollback(commit)

        assert success is True
        assert error is None

    @pytest.mark.asyncio
    async def test_health_check(self, backend):
        """Test health check simulation."""
        healthy, issues = await backend.health_check()

        assert healthy is True
        assert issues == []


class TestUpdateStatusEnum:
    """Tests for UpdateStatus enum."""

    def test_status_values(self):
        """Test that all expected status values exist."""
        assert UpdateStatus.PENDING.value == "pending"
        assert UpdateStatus.DOWNLOADING.value == "downloading"
        assert UpdateStatus.INSTALLING.value == "installing"
        assert UpdateStatus.MIGRATING.value == "migrating"
        assert UpdateStatus.RESTARTING.value == "restarting"
        assert UpdateStatus.COMPLETED.value == "completed"
        assert UpdateStatus.FAILED.value == "failed"
        assert UpdateStatus.ROLLED_BACK.value == "rolled_back"
        assert UpdateStatus.CANCELLED.value == "cancelled"


class TestUpdateChannelEnum:
    """Tests for UpdateChannel enum."""

    def test_channel_values(self):
        """Test that all expected channel values exist."""
        assert UpdateChannel.STABLE.value == "stable"
        assert UpdateChannel.BETA.value == "beta"


class TestUpdateHistory:
    """Tests for UpdateHistory model."""

    def test_create_update_history(self, db_session: Session):
        """Test creating an update history record."""
        history = UpdateHistory(
            from_version="1.4.2",
            to_version="1.5.0",
            channel=UpdateChannel.STABLE.value,
            from_commit="abc123" + "0" * 34,
            to_commit="def456" + "0" * 34,
            user_id=1,
        )
        db_session.add(history)
        db_session.commit()

        saved = db_session.query(UpdateHistory).filter(
            UpdateHistory.from_version == "1.4.2"
        ).first()

        assert saved is not None
        assert saved.to_version == "1.5.0"
        assert saved.status == UpdateStatus.PENDING.value

    def test_set_progress(self, db_session: Session):
        """Test setting progress on update record."""
        history = UpdateHistory(
            from_version="1.4.2",
            to_version="1.5.0",
            channel="stable",
            from_commit="a" * 40,
            to_commit="b" * 40,
        )
        db_session.add(history)
        db_session.commit()

        history.set_progress(50, "Installing dependencies...")
        db_session.commit()

        assert history.progress_percent == 50
        assert history.current_step == "Installing dependencies..."

    def test_set_progress_clamps_to_100(self, db_session: Session):
        """Test that progress is clamped to 100."""
        history = UpdateHistory(
            from_version="1.0.0",
            to_version="1.1.0",
            channel="stable",
            from_commit="a" * 40,
            to_commit="b" * 40,
        )
        db_session.add(history)
        db_session.commit()

        history.set_progress(150, "Overcomplete")
        assert history.progress_percent == 100

    def test_complete(self):
        """Test completing an update (unit test without DB)."""
        # Test the method directly without database
        history = UpdateHistory(
            from_version="1.4.2",
            to_version="1.5.0",
            channel="stable",
            from_commit="a" * 40,
            to_commit="b" * 40,
        )
        # Set started_at to None to skip duration calculation
        history.started_at = None

        history.complete()

        assert history.status == UpdateStatus.COMPLETED.value
        assert history.completed_at is not None
        assert history.progress_percent == 100
        assert history.current_step == "Update completed"

    def test_fail(self):
        """Test failing an update (unit test without DB)."""
        history = UpdateHistory(
            from_version="1.4.2",
            to_version="1.5.0",
            channel="stable",
            from_commit="a" * 40,
            to_commit="b" * 40,
        )
        history.started_at = None

        history.fail("Migration error")

        assert history.status == UpdateStatus.FAILED.value
        assert history.error_message == "Migration error"
        assert history.completed_at is not None

    def test_mark_rolled_back(self):
        """Test marking an update as rolled back (unit test without DB)."""
        history = UpdateHistory(
            from_version="1.4.2",
            to_version="1.5.0",
            channel="stable",
            from_commit="abc12345" + "0" * 32,
            to_commit="b" * 40,
        )
        history.started_at = None

        history.mark_rolled_back("abc12345" + "0" * 32)

        assert history.status == UpdateStatus.ROLLED_BACK.value
        assert history.rollback_commit == "abc12345" + "0" * 32

    def test_cancel(self):
        """Test cancelling an update (unit test without DB)."""
        history = UpdateHistory(
            from_version="1.4.2",
            to_version="1.5.0",
            channel="stable",
            from_commit="a" * 40,
            to_commit="b" * 40,
        )
        history.started_at = None

        history.cancel()

        assert history.status == UpdateStatus.CANCELLED.value
        assert history.current_step == "Update cancelled"


class TestUpdateConfig:
    """Tests for UpdateConfig model."""

    def test_create_config(self, db_session: Session):
        """Test creating update config."""
        config = UpdateConfig(
            auto_check_enabled=True,
            check_interval_hours=24,
            channel=UpdateChannel.STABLE.value,
            auto_backup_before_update=True,
            require_healthy_services=True,
        )
        db_session.add(config)
        db_session.commit()

        saved = db_session.query(UpdateConfig).first()

        assert saved is not None
        assert saved.auto_check_enabled is True
        assert saved.check_interval_hours == 24
        assert saved.channel == "stable"

    def test_config_defaults(self, db_session: Session):
        """Test config default values."""
        config = UpdateConfig(
            check_interval_hours=12,
        )
        db_session.add(config)
        db_session.commit()

        saved = db_session.query(UpdateConfig).first()

        assert saved.auto_check_enabled is True
        assert saved.auto_backup_before_update is True
        assert saved.require_healthy_services is True
        assert saved.auto_update_enabled is False


class TestUpdateService:
    """Tests for UpdateService class."""

    @pytest.fixture
    def mock_backend(self):
        """Create a mocked backend."""
        backend = MagicMock()
        backend.get_current_version = AsyncMock(return_value=MagicMock(
            version="1.4.2",
            commit="abc123" + "0" * 34,
            commit_short="abc123",
            tag="v1.4.2",
            date=datetime.now(timezone.utc),
        ))
        backend.check_for_updates = AsyncMock(return_value=(False, None, []))
        backend.health_check = AsyncMock(return_value=(True, []))
        return backend

    def test_service_init(self, db_session: Session, mock_backend):
        """Test UpdateService initialization."""
        service = UpdateService(db_session, backend=mock_backend)

        assert service.db is db_session
        assert service.backend is mock_backend

    def test_get_config_creates_default(self, db_session: Session, mock_backend):
        """Test that get_config creates default config if none exists."""
        service = UpdateService(db_session, backend=mock_backend)

        config = service.get_config()

        assert config is not None
        assert config.auto_check_enabled is True
        assert config.channel == "stable"

    def test_get_config_returns_existing(self, db_session: Session, mock_backend):
        """Test that get_config returns existing config."""
        # Create config
        existing = UpdateConfig(
            auto_check_enabled=False,
            check_interval_hours=12,
            channel="unstable",
        )
        db_session.add(existing)
        db_session.commit()

        service = UpdateService(db_session, backend=mock_backend)
        config = service.get_config()

        assert config.auto_check_enabled is False
        assert config.check_interval_hours == 12
        assert config.channel == "unstable"

    def test_progress_callbacks(self, db_session: Session, mock_backend):
        """Test registering and triggering progress callbacks."""
        service = UpdateService(db_session, backend=mock_backend)

        callback_calls = []
        def callback(percent, step):
            callback_calls.append((percent, step))

        service.add_progress_callback(callback)
        service._notify_progress(50, "Test step")

        assert len(callback_calls) == 1
        assert callback_calls[0] == (50, "Test step")

    def test_remove_progress_callback(self, db_session: Session, mock_backend):
        """Test removing progress callbacks."""
        service = UpdateService(db_session, backend=mock_backend)

        callback_calls = []
        def callback(percent, step):
            callback_calls.append((percent, step))

        service.add_progress_callback(callback)
        service.remove_progress_callback(callback)
        service._notify_progress(50, "Test step")

        assert len(callback_calls) == 0

    def test_get_history_empty(self, db_session: Session, mock_backend):
        """Test getting empty update history."""
        service = UpdateService(db_session, backend=mock_backend)

        history = service.get_history()

        assert history.total == 0
        assert history.updates == []
        assert history.page == 1

    def test_get_history_with_entries(self, db_session: Session, mock_backend):
        """Test getting update history with entries."""
        # Create some history
        for i in range(3):
            entry = UpdateHistory(
                from_version=f"1.{i}.0",
                to_version=f"1.{i+1}.0",
                channel="stable",
                from_commit="a" * 40,
                to_commit="b" * 40,
            )
            db_session.add(entry)
        db_session.commit()

        service = UpdateService(db_session, backend=mock_backend)
        history = service.get_history()

        assert history.total == 3
        assert len(history.updates) == 3

    def test_get_history_pagination(self, db_session: Session, mock_backend):
        """Test update history pagination."""
        # Create 5 entries
        for i in range(5):
            entry = UpdateHistory(
                from_version=f"1.{i}.0",
                to_version=f"1.{i+1}.0",
                channel="stable",
                from_commit="a" * 40,
                to_commit="b" * 40,
            )
            db_session.add(entry)
        db_session.commit()

        service = UpdateService(db_session, backend=mock_backend)

        # Get page 1 with size 2
        history = service.get_history(page=1, page_size=2)

        assert history.total == 5
        assert len(history.updates) == 2
        assert history.page == 1
        assert history.page_size == 2

    def test_get_update_progress_not_found(self, db_session: Session, mock_backend):
        """Test getting progress for non-existent update."""
        service = UpdateService(db_session, backend=mock_backend)

        progress = service.get_update_progress(9999)

        assert progress is None

    def test_get_update_progress_found(self, db_session: Session, mock_backend):
        """Test getting progress for existing update."""
        entry = UpdateHistory(
            from_version="1.4.2",
            to_version="1.5.0",
            channel="stable",
            from_commit="a" * 40,
            to_commit="b" * 40,
            status=UpdateStatus.DOWNLOADING.value,
        )
        entry.set_progress(45, "Downloading...")
        db_session.add(entry)
        db_session.commit()

        service = UpdateService(db_session, backend=mock_backend)
        progress = service.get_update_progress(entry.id)

        assert progress is not None
        assert progress.update_id == entry.id
        assert progress.status == "downloading"
        assert progress.progress_percent == 45
        assert progress.current_step == "Downloading..."


class TestGetUpdateBackend:
    """Tests for backend factory function."""

    def test_dev_mode_returns_dev_backend(self, monkeypatch):
        """Test that dev mode returns DevUpdateBackend."""
        from app.core import config as config_module

        mock_settings = MagicMock()
        mock_settings.is_dev_mode = True
        monkeypatch.setattr(config_module, "settings", mock_settings)

        # Re-import to get patched version
        from app.services.update import api as update_api
        monkeypatch.setattr(update_api, "settings", mock_settings)

        backend = update_api.get_update_backend()
        assert isinstance(backend, DevUpdateBackend)


class TestProdBackendGetCurrentVersion:
    """Tests for tag-based version detection in ProdUpdateBackend.get_current_version."""

    @pytest.fixture
    def backend(self):
        from app.services.update.prod_backend import ProdUpdateBackend
        return ProdUpdateBackend()

    @pytest.mark.asyncio
    async def test_head_on_prerelease_tag_uses_tag_as_version(self, backend):
        """When HEAD is on a pre-release tag, version reflects the full tag name."""
        def fake_run_git(*args):
            cmd = args
            if cmd[:3] == ("describe", "--tags", "--exact-match"):
                return True, "v1.31.7-pre.42", ""
            if cmd[:2] == ("rev-parse", "HEAD"):
                return True, "abc1234567890abcdef1234567890abcdef12345678", ""
            if cmd[:3] == ("log", "-1", "--format=%cI"):
                return True, "2026-05-06T10:00:00+00:00", ""
            return False, "", "unexpected"

        backend._run_git = fake_run_git
        info = await backend.get_current_version()
        assert info.version == "1.31.7-pre.42"
        assert info.tag == "v1.31.7-pre.42"
        assert info.is_prerelease is True
        assert info.is_dev_build is False
        assert info.commit_short == "abc1234"

    @pytest.mark.asyncio
    async def test_head_on_stable_tag_marks_not_prerelease(self, backend):
        """Stable tags have no -pre/-rc suffix and is_prerelease must be False."""
        def fake_run_git(*args):
            cmd = args
            if cmd[:3] == ("describe", "--tags", "--exact-match"):
                return True, "v1.32.0", ""
            if cmd[:2] == ("rev-parse", "HEAD"):
                return True, "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef", ""
            if cmd[:3] == ("log", "-1", "--format=%cI"):
                return True, "2026-05-06T10:00:00+00:00", ""
            return False, "", "unexpected"

        backend._run_git = fake_run_git
        info = await backend.get_current_version()
        assert info.version == "1.32.0"
        assert info.tag == "v1.32.0"
        assert info.is_prerelease is False
        assert info.is_dev_build is False

    @pytest.mark.asyncio
    async def test_head_between_tags_falls_back_to_pyproject(self, backend):
        """When HEAD is not on a tag (local dev), falls back to pyproject + is_dev_build=True."""
        def fake_run_git(*args):
            cmd = args
            if cmd[:3] == ("describe", "--tags", "--exact-match"):
                return False, "", "fatal: no exact match"
            if cmd[:2] == ("rev-parse", "HEAD"):
                return True, "feedfacefeedfacefeedfacefeedfacefeedface", ""
            if cmd[:3] == ("log", "-1", "--format=%cI"):
                return True, "2026-05-06T10:00:00+00:00", ""
            return False, "", "unexpected"

        backend._run_git = fake_run_git
        info = await backend.get_current_version()
        assert info.is_prerelease is False
        assert info.is_dev_build is True
        assert info.tag is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tag,expected", [
        ("v1.0.0-pre.1", True),
        ("v1.0.0-rc.1", True),
        ("v1.0.0-alpha", True),
        ("v1.0.0-beta", True),
        ("v1.0.0-unstable", True),
        ("v1.0.0", False),
        ("v2.5.10", False),
    ])
    async def test_prerelease_detection_by_tag_suffix(self, backend, tag, expected):
        def fake_run_git(*args):
            cmd = args
            if cmd[:3] == ("describe", "--tags", "--exact-match"):
                return True, tag, ""
            if cmd[:2] == ("rev-parse", "HEAD"):
                return True, "0" * 40, ""
            if cmd[:3] == ("log", "-1", "--format=%cI"):
                return True, "2026-05-06T10:00:00+00:00", ""
            return False, "", ""
        backend._run_git = fake_run_git
        info = await backend.get_current_version()
        assert info.is_prerelease is expected
