"""Push notification on automatic mobile device deactivation/expiry (#228).

When a device's authorization expires, ``verify_mobile_device_token`` auto-
deactivates it and raises 401. Previously this happened silently — the
``device_removed`` push (which the app already handles to log out cleanly) was
only sent on *manual* deletion. These tests pin the best-effort push on the
automatic-expiry path.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.deps import verify_mobile_device_token
from app.models.mobile import MobileDevice
from app.services import auth as auth_service


def _make_request(device_id: str) -> Request:
    """Build a minimal Starlette request carrying the X-Device-ID header."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/mobile/ping",
        "headers": [(b"x-device-id", device_id.encode())],
        "query_string": b"",
        "client": ("127.0.0.1", 1234),
    }
    return Request(scope)


def _add_device(db_session, user, *, push_token, expires_at):
    device = MobileDevice(
        user_id=str(user.id),
        device_name="Expired Phone",
        device_type="android",
        push_token=push_token,
        is_active=True,
        expires_at=expires_at,
    )
    db_session.add(device)
    db_session.commit()
    db_session.refresh(device)
    return device


def test_expired_device_sends_removal_push(db_session, regular_user):
    """An expired device gets a device_removed push before the 401 (#228)."""
    device = _add_device(
        db_session, regular_user,
        push_token="fake-fcm-expired",
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    token = auth_service.create_access_token(regular_user)
    request = _make_request(str(device.id))

    with patch(
        "app.services.notifications.firebase.FirebaseService.is_available",
        return_value=True,
    ), patch(
        "app.services.notifications.firebase.FirebaseService.send_device_removed_notification"
    ) as mock_push:
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                verify_mobile_device_token(request=request, token=token, db=db_session)
            )

    assert exc_info.value.status_code == 401
    mock_push.assert_called_once_with(
        device_token="fake-fcm-expired",
        device_name="Expired Phone",
    )
    # Device is still auto-deactivated.
    db_session.refresh(device)
    assert device.is_active is False


def test_expired_device_without_push_token_does_not_send(db_session, regular_user):
    """No push token → no push attempt, but still 401 + deactivation."""
    device = _add_device(
        db_session, regular_user,
        push_token=None,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    token = auth_service.create_access_token(regular_user)
    request = _make_request(str(device.id))

    with patch(
        "app.services.notifications.firebase.FirebaseService.is_available",
        return_value=True,
    ), patch(
        "app.services.notifications.firebase.FirebaseService.send_device_removed_notification"
    ) as mock_push:
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                verify_mobile_device_token(request=request, token=token, db=db_session)
            )

    assert exc_info.value.status_code == 401
    mock_push.assert_not_called()
    db_session.refresh(device)
    assert device.is_active is False


def test_push_failure_does_not_block_logout(db_session, regular_user):
    """A failing push must not swallow the 401 — logout still happens (#228)."""
    device = _add_device(
        db_session, regular_user,
        push_token="fake-fcm-expired",
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    token = auth_service.create_access_token(regular_user)
    request = _make_request(str(device.id))

    with patch(
        "app.services.notifications.firebase.FirebaseService.is_available",
        return_value=True,
    ), patch(
        "app.services.notifications.firebase.FirebaseService.send_device_removed_notification",
        side_effect=RuntimeError("FCM down"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                verify_mobile_device_token(request=request, token=token, db=db_session)
            )

    assert exc_info.value.status_code == 401
    db_session.refresh(device)
    assert device.is_active is False
