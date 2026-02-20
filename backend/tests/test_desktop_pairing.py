"""Tests for the Desktop Device Code Flow (BaluDesk pairing)."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.desktop_pairing import DesktopPairingCode
from app.models.sync_state import SyncState
from app.models.user import User
from app.services.desktop_pairing import DesktopPairingService
from app.schemas.desktop_pairing import DeviceCodeRequest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

API_PREFIX = settings.api_prefix

DEVICE_PAYLOAD = {
    "device_id": "test-uuid-1234",
    "device_name": "My BaluDesk PC",
    "platform": "windows",
}


def _request_code(client: TestClient) -> dict:
    """Helper to request a device code and return the JSON response."""
    resp = client.post(f"{API_PREFIX}/desktop-pairing/device-code", json=DEVICE_PAYLOAD)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Service-layer tests (unit)
# ---------------------------------------------------------------------------

class TestDesktopPairingService:
    """Unit tests for DesktopPairingService."""

    def test_request_device_code(self, db_session: Session):
        """Requesting a code returns valid device_code and user_code."""
        req = DeviceCodeRequest(**DEVICE_PAYLOAD)
        result = DesktopPairingService.request_device_code(db_session, req, "http://localhost:3001")

        assert len(result.device_code) > 20  # high-entropy
        assert result.user_code.isdigit() and len(result.user_code) == 6
        assert result.expires_in == 600
        assert result.interval == 5
        assert "pair=1" in result.verification_url

        # Check DB record was created
        record = db_session.query(DesktopPairingCode).filter_by(device_code=result.device_code).first()
        assert record is not None
        assert record.status == "pending"
        assert record.device_name == "My BaluDesk PC"

    def test_unique_user_codes(self, db_session: Session):
        """Multiple requests produce unique user_codes."""
        req = DeviceCodeRequest(**DEVICE_PAYLOAD)
        codes = set()
        for _ in range(5):
            result = DesktopPairingService.request_device_code(db_session, req, "http://localhost:3001")
            codes.add(result.user_code)
        assert len(codes) == 5

    def test_verify_code_success(self, db_session: Session):
        """Verifying a valid code returns device info."""
        req = DeviceCodeRequest(**DEVICE_PAYLOAD)
        result = DesktopPairingService.request_device_code(db_session, req, "http://localhost:3001")

        info = DesktopPairingService.verify_code(db_session, result.user_code)
        assert info.device_name == "My BaluDesk PC"
        assert info.platform == "windows"
        assert info.device_id == "test-uuid-1234"

    def test_verify_code_invalid(self, db_session: Session):
        """Verifying a non-existent code raises 404."""
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            DesktopPairingService.verify_code(db_session, "000000")
        assert exc_info.value.status_code == 404

    def test_verify_code_expired(self, db_session: Session):
        """Verifying an expired code raises 410."""
        req = DeviceCodeRequest(**DEVICE_PAYLOAD)
        result = DesktopPairingService.request_device_code(db_session, req, "http://localhost:3001")

        # Expire the code manually
        record = db_session.query(DesktopPairingCode).filter_by(device_code=result.device_code).first()
        record.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db_session.commit()

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            DesktopPairingService.verify_code(db_session, result.user_code)
        assert exc_info.value.status_code == 410

    def test_approve_and_poll(self, db_session: Session, regular_user: User):
        """Full approve→poll flow returns tokens and creates SyncState."""
        req = DeviceCodeRequest(**DEVICE_PAYLOAD)
        result = DesktopPairingService.request_device_code(db_session, req, "http://localhost:3001")

        # Approve
        DesktopPairingService.approve_code(db_session, result.user_code, regular_user.id)

        # Poll — should return tokens
        poll = DesktopPairingService.poll_device_code(db_session, result.device_code)
        assert poll.status == "approved"
        assert poll.access_token is not None
        assert poll.refresh_token is not None
        assert poll.token_type == "bearer"
        assert poll.user["username"] == regular_user.username

        # Pairing record should be deleted (one-time delivery)
        record = db_session.query(DesktopPairingCode).filter_by(device_code=result.device_code).first()
        assert record is None

        # SyncState should be created
        sync = db_session.query(SyncState).filter_by(
            user_id=regular_user.id,
            device_id="test-uuid-1234",
        ).first()
        assert sync is not None
        assert sync.device_name == "My BaluDesk PC"

    def test_deny_code(self, db_session: Session):
        """Denying a code changes its status."""
        req = DeviceCodeRequest(**DEVICE_PAYLOAD)
        result = DesktopPairingService.request_device_code(db_session, req, "http://localhost:3001")

        DesktopPairingService.deny_code(db_session, result.user_code)

        poll = DesktopPairingService.poll_device_code(db_session, result.device_code)
        assert poll.status == "denied"

    def test_poll_pending(self, db_session: Session):
        """Polling a pending code returns authorization_pending."""
        req = DeviceCodeRequest(**DEVICE_PAYLOAD)
        result = DesktopPairingService.request_device_code(db_session, req, "http://localhost:3001")

        poll = DesktopPairingService.poll_device_code(db_session, result.device_code)
        assert poll.status == "authorization_pending"

    def test_poll_expired(self, db_session: Session):
        """Polling an expired code returns expired status."""
        req = DeviceCodeRequest(**DEVICE_PAYLOAD)
        result = DesktopPairingService.request_device_code(db_session, req, "http://localhost:3001")

        record = db_session.query(DesktopPairingCode).filter_by(device_code=result.device_code).first()
        record.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db_session.commit()

        poll = DesktopPairingService.poll_device_code(db_session, result.device_code)
        assert poll.status == "expired"

    def test_poll_invalid_device_code(self, db_session: Session):
        """Polling with an invalid device_code raises 404."""
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            DesktopPairingService.poll_device_code(db_session, "nonexistent")
        assert exc_info.value.status_code == 404

    def test_brute_force_protection(self, db_session: Session):
        """After 5 failed attempts the code is auto-denied."""
        req = DeviceCodeRequest(**DEVICE_PAYLOAD)
        result = DesktopPairingService.request_device_code(db_session, req, "http://localhost:3001")

        for _ in range(5):
            DesktopPairingService.increment_failed_attempts(db_session, result.user_code)

        record = db_session.query(DesktopPairingCode).filter_by(device_code=result.device_code).first()
        assert record.status == "denied"
        assert record.failed_attempts == 5

    def test_cleanup_expired(self, db_session: Session):
        """Cleanup removes codes expired >1 hour ago."""
        req = DeviceCodeRequest(**DEVICE_PAYLOAD)
        result = DesktopPairingService.request_device_code(db_session, req, "http://localhost:3001")

        # Expire the code by >1 hour
        record = db_session.query(DesktopPairingCode).filter_by(device_code=result.device_code).first()
        record.expires_at = datetime.now(timezone.utc) - timedelta(hours=2)
        db_session.commit()

        DesktopPairingService._cleanup_expired(db_session)

        assert db_session.query(DesktopPairingCode).filter_by(device_code=result.device_code).first() is None


# ---------------------------------------------------------------------------
# API-layer tests (integration)
# ---------------------------------------------------------------------------

class TestDesktopPairingAPI:
    """Integration tests for desktop-pairing API routes."""

    def test_device_code_endpoint(self, client: TestClient):
        """POST /desktop-pairing/device-code creates a code."""
        data = _request_code(client)
        assert "device_code" in data
        assert "user_code" in data
        assert len(data["user_code"]) == 6
        assert data["expires_in"] == 600
        assert data["interval"] == 5

    def test_poll_endpoint_pending(self, client: TestClient):
        """POST /desktop-pairing/poll returns authorization_pending for new code."""
        code_data = _request_code(client)
        resp = client.post(
            f"{API_PREFIX}/desktop-pairing/poll",
            json={"device_code": code_data["device_code"]},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "authorization_pending"

    def test_poll_endpoint_invalid(self, client: TestClient):
        """POST /desktop-pairing/poll with bad code returns 404."""
        resp = client.post(
            f"{API_PREFIX}/desktop-pairing/poll",
            json={"device_code": "nonexistent-code"},
        )
        assert resp.status_code == 404

    def test_verify_requires_auth(self, client: TestClient):
        """POST /desktop-pairing/verify requires authentication."""
        resp = client.post(
            f"{API_PREFIX}/desktop-pairing/verify",
            json={"user_code": "123456"},
        )
        assert resp.status_code == 401

    def test_approve_requires_auth(self, client: TestClient):
        """POST /desktop-pairing/approve requires authentication."""
        resp = client.post(
            f"{API_PREFIX}/desktop-pairing/approve",
            json={"user_code": "123456"},
        )
        assert resp.status_code == 401

    def test_deny_requires_auth(self, client: TestClient):
        """POST /desktop-pairing/deny requires authentication."""
        resp = client.post(
            f"{API_PREFIX}/desktop-pairing/deny",
            json={"user_code": "123456"},
        )
        assert resp.status_code == 401

    def test_full_flow(self, client: TestClient, user_headers: dict):
        """Full end-to-end flow: request → verify → approve → poll."""
        # 1. Request code (unauthenticated)
        code_data = _request_code(client)

        # 2. Verify (authenticated)
        resp = client.post(
            f"{API_PREFIX}/desktop-pairing/verify",
            json={"user_code": code_data["user_code"]},
            headers=user_headers,
        )
        assert resp.status_code == 200
        info = resp.json()
        assert info["device_name"] == "My BaluDesk PC"
        assert info["platform"] == "windows"

        # 3. Approve (authenticated)
        resp = client.post(
            f"{API_PREFIX}/desktop-pairing/approve",
            json={"user_code": code_data["user_code"]},
            headers=user_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

        # 4. Poll — tokens delivered
        resp = client.post(
            f"{API_PREFIX}/desktop-pairing/poll",
            json={"device_code": code_data["device_code"]},
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["status"] == "approved"
        assert result["access_token"] is not None
        assert result["refresh_token"] is not None
        assert result["user"] is not None

        # 5. Second poll should fail (one-time delivery)
        resp = client.post(
            f"{API_PREFIX}/desktop-pairing/poll",
            json={"device_code": code_data["device_code"]},
        )
        assert resp.status_code == 404

    def test_deny_flow(self, client: TestClient, user_headers: dict):
        """Request → deny → poll returns denied."""
        code_data = _request_code(client)

        resp = client.post(
            f"{API_PREFIX}/desktop-pairing/deny",
            json={"user_code": code_data["user_code"]},
            headers=user_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "denied"

        resp = client.post(
            f"{API_PREFIX}/desktop-pairing/poll",
            json={"device_code": code_data["device_code"]},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "denied"

    def test_invalid_platform(self, client: TestClient):
        """Platform must be windows, mac, or linux."""
        resp = client.post(
            f"{API_PREFIX}/desktop-pairing/device-code",
            json={"device_id": "x", "device_name": "x", "platform": "bsd"},
        )
        assert resp.status_code == 422

    def test_invalid_user_code_format(self, client: TestClient, user_headers: dict):
        """user_code must be exactly 6 digits."""
        resp = client.post(
            f"{API_PREFIX}/desktop-pairing/verify",
            json={"user_code": "abc"},
            headers=user_headers,
        )
        assert resp.status_code == 422

    def test_verify_nonexistent_code(self, client: TestClient, user_headers: dict):
        """Verifying a code that doesn't exist returns 404."""
        resp = client.post(
            f"{API_PREFIX}/desktop-pairing/verify",
            json={"user_code": "999999"},
            headers=user_headers,
        )
        assert resp.status_code == 404
