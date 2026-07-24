"""Both gates for unlocking the desktop session, plus the audit trail."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.models.power_permissions import UserPowerPermission
from app.services.power import session_lock

LAN = "192.168.178.29"
VPN = "10.8.0.3"
# NOTE: deviates from the brief's literal "203.0.113.7". That address is the
# RFC 5737 documentation range (TEST-NET-3); Python's ipaddress.is_private
# treats it (and 192.0.2.0/24, 198.51.100.0/24) as "private" because it is
# merely "not globally routable", not because it is a real LAN/VPN range. That
# makes app/core/network_utils.is_private_or_local_ip() wrongly ALLOW it,
# which is a pre-existing gap in shared code out of this task's scope - see
# the flagged finding in the task report. 8.8.8.8 is unambiguously global.
PUBLIC = "8.8.8.8"


def _admin():
    return SimpleNamespace(id=1, username="admin", role="admin")


def _user(user_id: int):
    return SimpleNamespace(id=user_id, username="sven", role="user")


@pytest.fixture
def unlock_called():
    """Replaces the backend so no loginctl is ever invoked."""
    backend = MagicMock()
    backend.unlock.return_value = (True, "session 2 unlocked")
    with patch.object(session_lock, "get_session_lock_backend", return_value=backend):
        yield backend


@pytest.fixture(autouse=True)
def _silent_audit():
    with patch.object(session_lock, "get_audit_logger_db") as factory:
        factory.return_value = MagicMock()
        yield factory.return_value


class TestPermissionGate:
    async def test_admin_from_lan_unlocks(self, db_session, unlock_called):
        ok, _detail = await session_lock.unlock_if_permitted(
            user=_admin(), client_host=LAN, db=db_session
        )

        assert ok is True
        unlock_called.unlock.assert_called_once()

    async def test_delegated_user_with_the_permission_unlocks(
        self, db_session, regular_user, unlock_called
    ):
        db_session.add(
            UserPowerPermission(user_id=regular_user.id, can_unlock_session=True)
        )
        db_session.commit()

        ok, _detail = await session_lock.unlock_if_permitted(
            user=_user(regular_user.id), client_host=LAN, db=db_session
        )

        assert ok is True
        unlock_called.unlock.assert_called_once()

    async def test_user_without_the_permission_is_refused(
        self, db_session, regular_user, unlock_called
    ):
        ok, detail = await session_lock.unlock_if_permitted(
            user=_user(regular_user.id), client_host=LAN, db=db_session
        )

        assert ok is False
        assert "permission" in detail
        unlock_called.unlock.assert_not_called()


class TestNetworkGate:
    async def test_vpn_is_allowed(self, db_session, unlock_called):
        ok, _detail = await session_lock.unlock_if_permitted(
            user=_admin(), client_host=VPN, db=db_session
        )

        assert ok is True

    async def test_public_address_is_refused_even_for_an_admin(
        self, db_session, unlock_called
    ):
        """The web app is reachable from the open internet via duckdns. This
        assertion is the one that fails if the IP gate ever breaks - testing
        only the allowed direction would stay green on a wide-open gate."""
        ok, detail = await session_lock.unlock_if_permitted(
            user=_admin(), client_host=PUBLIC, db=db_session
        )

        assert ok is False
        assert "network" in detail
        unlock_called.unlock.assert_not_called()

    async def test_missing_client_host_is_refused(self, db_session, unlock_called):
        ok, _detail = await session_lock.unlock_if_permitted(
            user=_admin(), client_host=None, db=db_session
        )

        assert ok is False
        unlock_called.unlock.assert_not_called()


class TestAuditTrail:
    async def test_successful_unlock_is_audited(
        self, db_session, unlock_called, _silent_audit
    ):
        await session_lock.unlock_if_permitted(
            user=_admin(), client_host=LAN, db=db_session
        )

        _silent_audit.log_event.assert_called_once()
        kwargs = _silent_audit.log_event.call_args.kwargs
        assert kwargs["action"] == "desktop_unlock_session"
        assert kwargs["event_type"] == "POWER"

    async def test_a_refused_unlock_writes_no_audit_noise(
        self, db_session, unlock_called, _silent_audit
    ):
        await session_lock.unlock_if_permitted(
            user=_admin(), client_host=PUBLIC, db=db_session
        )

        _silent_audit.log_event.assert_not_called()

    async def test_delegated_user_also_gets_a_security_event(
        self, db_session, regular_user, unlock_called, _silent_audit
    ):
        db_session.add(
            UserPowerPermission(user_id=regular_user.id, can_unlock_session=True)
        )
        db_session.commit()

        await session_lock.unlock_if_permitted(
            user=_user(regular_user.id), client_host=LAN, db=db_session
        )

        _silent_audit.log_security_event.assert_called_once()

    async def test_an_admin_gets_no_delegated_security_event(
        self, db_session, unlock_called, _silent_audit
    ):
        """The security event marks a DELEGATED user exercising a privileged
        action - for an admin it would just be noise."""
        await session_lock.unlock_if_permitted(
            user=_admin(), client_host=LAN, db=db_session
        )

        _silent_audit.log_security_event.assert_not_called()

    async def test_a_failed_unlock_is_audited_as_a_failure(
        self, db_session, unlock_called, _silent_audit
    ):
        """Gates passed, loginctl did not deliver. Without this the function
        would report success=True over a still-locked screen."""
        unlock_called.unlock.return_value = (False, "session 2 still reports LockedHint=yes")

        ok, _detail = await session_lock.unlock_if_permitted(
            user=_admin(), client_host=LAN, db=db_session
        )

        assert ok is False
        kwargs = _silent_audit.log_event.call_args.kwargs
        assert kwargs["success"] is False
        assert kwargs["ip_address"] == LAN
