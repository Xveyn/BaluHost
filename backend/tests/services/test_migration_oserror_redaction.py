"""Tests for MigrationService._validate_paths OSError detail stripping (issue #258)."""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from sqlalchemy.orm import Session

from app.services.cache.migration import MigrationService


@pytest.fixture
def migration_service(db_session: Session) -> MigrationService:
    return MigrationService(db_session)


def test_not_writable_raises_valueerror_without_oserror_detail(
    migration_service: MigrationService,
    tmp_path: Path,
):
    """OSError errno/path detail must NOT appear in the raised ValueError message."""
    source = tmp_path / "source"
    source.mkdir()
    dest = tmp_path / "dest"

    # Simulate a Permission-denied OSError when the writability probe runs.
    os_error = OSError(13, "Permission denied", str(dest / ".migration_test"))

    with patch.object(Path, "write_text", side_effect=os_error):
        with pytest.raises(ValueError) as exc_info:
            migration_service._validate_paths(str(source), str(dest), check_writable=True)

    msg = str(exc_info.value)
    assert msg == "Destination path not writable"
    # Ensure no errno or path leaks through
    assert "13" not in msg
    assert "Permission denied" not in msg
    assert ".migration_test" not in msg


def test_not_writable_logs_oserror_detail(
    migration_service: MigrationService,
    tmp_path: Path,
):
    """The OSError detail MUST be logged server-side so it is not silently swallowed."""
    source = tmp_path / "source"
    source.mkdir()
    dest = tmp_path / "dest"

    os_error = OSError(13, "Permission denied", str(dest / ".migration_test"))

    with patch("app.services.cache.migration.logger") as mock_logger:
        with patch.object(Path, "write_text", side_effect=os_error):
            with pytest.raises(ValueError):
                migration_service._validate_paths(str(source), str(dest), check_writable=True)

        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        # The OSError should be passed as an argument (lazy % formatting)
        assert os_error in call_args.args or os_error in call_args.kwargs.values()
