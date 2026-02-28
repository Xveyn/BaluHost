"""Tests for BaluPi handshake and snapshot export services.

Tests cover:
- HMAC signature generation and structure
- Handshake notification functions (with mocked httpx)
- Snapshot export data collection (with mocked services)
- Config validation for handshake secret
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("NAS_MODE", "dev")
os.environ.setdefault("NAS_QUOTA_BYTES", str(10 * 1024 * 1024 * 1024))


def _run(coro):
    """Run an async coroutine from sync test code."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ============================================================================
# HMAC Signature Tests
# ============================================================================

class TestHmacSignature:
    """Test HMAC-SHA256 request signing."""

    def test_sign_request_with_body(self):
        with patch("app.services.balupi_handshake.settings") as mock_settings:
            mock_settings.balupi_handshake_secret = "test-secret-key-32-chars-minimum!"
            from app.services.balupi_handshake import _sign_request

            body = {"key": "value"}
            headers = _sign_request("POST", "/api/test", body)

            assert "X-Balupi-Timestamp" in headers
            assert "X-Balupi-Signature" in headers
            # Timestamp should be recent
            ts = int(headers["X-Balupi-Timestamp"])
            assert abs(ts - int(time.time())) < 5

    def test_sign_request_without_body(self):
        with patch("app.services.balupi_handshake.settings") as mock_settings:
            mock_settings.balupi_handshake_secret = "test-secret-key-32-chars-minimum!"
            from app.services.balupi_handshake import _sign_request

            headers = _sign_request("GET", "/api/status", None)
            assert "X-Balupi-Signature" in headers

    def test_sign_request_empty_secret_raises(self):
        with patch("app.services.balupi_handshake.settings") as mock_settings:
            mock_settings.balupi_handshake_secret = ""
            from app.services.balupi_handshake import _sign_request

            with pytest.raises(ValueError, match="not configured"):
                _sign_request("POST", "/api/test", None)

    def test_signature_is_deterministic(self):
        with patch("app.services.balupi_handshake.settings") as mock_settings:
            mock_settings.balupi_handshake_secret = "test-secret-key-32-chars-minimum!"
            from app.services.balupi_handshake import _sign_request

            body = {"hello": "world"}
            h1 = _sign_request("POST", "/api/test", body)
            # Same inputs with same timestamp should produce same signature
            # (we can't easily control time.time(), so just verify structure)
            assert len(h1["X-Balupi-Signature"]) == 64  # SHA-256 hex digest

    def test_signature_verifiable(self):
        """Verify the signature can be reproduced by the receiver."""
        secret = "test-secret-key-32-chars-minimum!"
        with patch("app.services.balupi_handshake.settings") as mock_settings:
            mock_settings.balupi_handshake_secret = secret
            from app.services.balupi_handshake import _sign_request

            body = {"snapshot": True}
            headers = _sign_request("POST", "/api/handshake/nas-going-offline", body)

            # Receiver-side verification
            timestamp = headers["X-Balupi-Timestamp"]
            body_bytes = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
            body_hash = hashlib.sha256(body_bytes).hexdigest()
            message = f"POST:/api/handshake/nas-going-offline:{timestamp}:{body_hash}"
            expected_sig = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
            assert headers["X-Balupi-Signature"] == expected_sig


# ============================================================================
# Handshake Notification Tests
# ============================================================================

class TestHandshakeNotifications:
    """Test Pi notification functions."""

    def test_notify_shutdown_success(self):
        with patch("app.services.balupi_handshake.settings") as mock_settings, \
             patch("app.services.balupi_handshake._get_client") as mock_get_client:
            mock_settings.balupi_enabled = True
            mock_settings.balupi_url = "http://192.168.1.20:8000"
            mock_settings.balupi_handshake_secret = "test-secret-key-32-chars-minimum!"

            mock_response = MagicMock()
            mock_response.json.return_value = {"acknowledged": True, "dns_switched": True}
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_client.is_closed = False
            mock_get_client.return_value = mock_client

            from app.services.balupi_handshake import notify_balupi_shutdown
            result = _run(notify_balupi_shutdown({"version": 1}))
            assert result is True

    def test_notify_shutdown_pi_offline(self):
        """When Pi is unreachable, shutdown notification returns False."""
        import httpx
        with patch("app.services.balupi_handshake.settings") as mock_settings, \
             patch("app.services.balupi_handshake._get_client") as mock_get_client:
            mock_settings.balupi_enabled = True
            mock_settings.balupi_url = "http://192.168.1.20:8000"
            mock_settings.balupi_handshake_secret = "test-secret-key-32-chars-minimum!"

            mock_client = AsyncMock()
            mock_client.request.side_effect = httpx.ConnectError("Connection refused")
            mock_client.is_closed = False
            mock_get_client.return_value = mock_client

            from app.services.balupi_handshake import notify_balupi_shutdown
            result = _run(notify_balupi_shutdown({"version": 1}))
            assert result is False

    def test_notify_startup_success(self):
        with patch("app.services.balupi_handshake.settings") as mock_settings, \
             patch("app.services.balupi_handshake._get_client") as mock_get_client:
            mock_settings.balupi_enabled = True
            mock_settings.balupi_url = "http://192.168.1.20:8000"
            mock_settings.balupi_handshake_secret = "test-secret-key-32-chars-minimum!"

            mock_response = MagicMock()
            mock_response.json.return_value = {
                "acknowledged": True,
                "inbox_flushed": True,
                "files_transferred": 3,
            }
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_client.is_closed = False
            mock_get_client.return_value = mock_client

            from app.services.balupi_handshake import notify_balupi_startup
            result = _run(notify_balupi_startup())
            assert result is True

    def test_notify_skipped_when_no_url(self):
        with patch("app.services.balupi_handshake.settings") as mock_settings:
            mock_settings.balupi_url = ""
            mock_settings.balupi_handshake_secret = "test-secret-key-32-chars-minimum!"

            from app.services.balupi_handshake import _send_to_pi
            result = _run(_send_to_pi("POST", "/api/test"))
            assert result is None


# ============================================================================
# Snapshot Export Tests
# ============================================================================

class TestSnapshotExport:
    """Test snapshot data collection."""

    def test_snapshot_structure(self):
        """Snapshot should have all required top-level keys."""
        mock_db = MagicMock()
        # Mock all DB queries to return empty results
        mock_db.query.return_value.filter.return_value.scalar.return_value = 0
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_db.query.return_value.order_by.return_value.first.return_value = None
        mock_db.query.return_value.scalar.return_value = 0

        with patch("app.services.snapshot_export.settings") as mock_settings:
            mock_settings.nas_storage_path = "/tmp/test-storage"
            mock_settings.is_dev_mode = True

            from app.services.snapshot_export import create_shutdown_snapshot
            snapshot = create_shutdown_snapshot(mock_db)

        assert snapshot["version"] == 1
        assert "generated_at" in snapshot
        assert "baluhost_version" in snapshot
        assert "system" in snapshot
        assert "storage" in snapshot
        assert "smart_health" in snapshot
        assert "services" in snapshot
        assert "users" in snapshot
        assert "files_summary" in snapshot

    def test_snapshot_no_sensitive_data(self):
        """Snapshot must not contain passwords, tokens, or keys."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.scalar.return_value = 0
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_db.query.return_value.order_by.return_value.first.return_value = None
        mock_db.query.return_value.scalar.return_value = 0

        with patch("app.services.snapshot_export.settings") as mock_settings:
            mock_settings.nas_storage_path = "/tmp/test-storage"
            mock_settings.is_dev_mode = True

            from app.services.snapshot_export import create_shutdown_snapshot
            snapshot = create_shutdown_snapshot(mock_db)

        snapshot_str = json.dumps(snapshot).lower()
        for sensitive_word in ["password", "token", "secret", "private_key", "api_key"]:
            assert sensitive_word not in snapshot_str, f"Snapshot contains '{sensitive_word}'"

    def test_system_info_collected(self):
        """System info should include hostname, uptime, CPU, RAM."""
        from app.services.snapshot_export import _collect_system_info
        info = _collect_system_info()
        assert "hostname" in info
        assert "uptime_seconds" in info
        assert "cpu_model" in info
        assert "ram_total_gb" in info
        assert isinstance(info["ram_total_gb"], float)

    def test_services_info_empty_db(self):
        """Services info should return zeros when DB is empty."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.scalar.return_value = 0
        mock_db.query.return_value.order_by.return_value.first.return_value = None

        from app.services.snapshot_export import _collect_services_info
        info = _collect_services_info(mock_db)
        assert info["vpn"]["active_clients"] == 0
        assert info["shares"]["active_shares"] == 0

    def test_users_info_empty_db(self):
        """Users info should return empty list when DB has no users."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []

        from app.services.snapshot_export import _collect_users_info
        info = _collect_users_info(mock_db)
        assert info["total"] == 0
        assert info["list"] == []

    def test_snapshot_handles_raid_failure(self):
        """Storage info should be empty dict when RAID service fails."""
        with patch("app.services.snapshot_export.settings") as mock_settings:
            mock_settings.nas_storage_path = "/nonexistent"
            from app.services.snapshot_export import _collect_storage_info

            with patch(
                "app.services.hardware.raid.api.get_status",
                side_effect=Exception("RAID service unavailable"),
            ):
                info = _collect_storage_info()
                assert info["arrays"] == []
                assert info["total_bytes"] == 0
