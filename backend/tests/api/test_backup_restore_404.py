"""Tests that restore_backup returns 404 (not 500) for unknown backup (issue #258)."""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.core.config import settings


def test_restore_unknown_backup_returns_404(client: TestClient, admin_headers: dict):
    """A restore request for a non-existent backup_id must return 404, not 500.

    Before the fix, the HTTPException(404) raised inside the try-block was caught
    by the broad `except Exception` handler and re-wrapped as 500.
    """
    nonexistent_id = 999999
    response = client.post(
        f"{settings.api_prefix}/backups/{nonexistent_id}/restore",
        json={
            "backup_id": nonexistent_id,
            "confirm": True,
            "restore_database": False,
            "restore_files": False,
            "restore_config": False,
        },
        headers=admin_headers,
    )
    assert response.status_code == 404, (
        f"Expected 404 but got {response.status_code}: {response.text}"
    )


def test_restore_missing_confirm_returns_400(client: TestClient, admin_headers: dict):
    """Sanity: confirm=False returns 400 before the service is even called."""
    nonexistent_id = 999999
    response = client.post(
        f"{settings.api_prefix}/backups/{nonexistent_id}/restore",
        json={
            "backup_id": nonexistent_id,
            "confirm": False,
            "restore_database": False,
            "restore_files": False,
            "restore_config": False,
        },
        headers=admin_headers,
    )
    assert response.status_code == 400
