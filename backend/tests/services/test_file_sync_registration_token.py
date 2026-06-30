"""Regression tests for FileSyncService.validate_registration_token (#241).

MobileRegistrationToken.expires_at is a naive DateTime column; comparing it
directly against an aware datetime.now(timezone.utc) raises TypeError. This
path is reachable via POST /api/sync/register (desktop/BaluDesk token-based
registration) and previously had no guard.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models.mobile import MobileRegistrationToken
from app.services.sync.file_sync import FileSyncService


def _make_token(db_session, user, expires_at, used=False):
    token = MobileRegistrationToken(
        token="reg_test_token",
        user_id=user.id,
        device_name="Test Desktop",
        expires_at=expires_at,
        used=used,
    )
    db_session.add(token)
    db_session.commit()
    return token


def test_validate_registration_token_accepts_naive_unexpired_token(db_session, regular_user):
    """A naive (no tzinfo) expires_at in the future must not raise TypeError."""
    naive_future = (datetime.now(timezone.utc) + timedelta(minutes=5)).replace(tzinfo=None)
    _make_token(db_session, regular_user, naive_future)

    service = FileSyncService(db_session)
    record = service.validate_registration_token("reg_test_token", regular_user.id)

    assert record.token == "reg_test_token"


def test_validate_registration_token_rejects_naive_expired_token(db_session, regular_user):
    """A naive (no tzinfo) expires_at in the past must raise ValueError, not TypeError."""
    naive_past = (datetime.now(timezone.utc) - timedelta(minutes=5)).replace(tzinfo=None)
    _make_token(db_session, regular_user, naive_past)

    service = FileSyncService(db_session)
    with pytest.raises(ValueError, match="expired"):
        service.validate_registration_token("reg_test_token", regular_user.id)
