"""Wiring tests for the notification state fan-out (see `_notification_fanout.py`).

Companion to `tests/api/test_notification_fanout.py`, which tests the
`fanout_state` helper in isolation (given an action, does it do the right
websocket calls). These tests cover the *other* half of the same seam: that
each of the eight call sites in `app/api/routes/notifications.py` passes the
helper the action string and id list promised in the helper module's
docstring table. A swapped `"read"`/`"dismissed"`, or a stale id, would leave
every route test in `test_notifications_routes.py` green (those only assert
on the HTTP response / DB content) and only surface in production.

Kept as a separate file rather than a new class in `test_notifications_routes.py`:
that file is pure black-box integration (real DB content, no mocks). These
tests patch `notifications.fanout_state` itself and inspect call arguments,
which is a different testing style worth keeping visually distinct — and it
mirrors `tests/api/test_notification_fanout.py` living apart from the plain
route tests too.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.models.notification import Notification


def _notification(user_id: int, *, trashed: bool = False) -> Notification:
    return Notification(
        user_id=user_id,
        category="system",
        notification_type="info",
        title="t",
        message="m",
        deleted_at=datetime.now(timezone.utc) if trashed else None,
    )


@pytest.fixture
def mock_fanout():
    """Patches the call site, not the helper: proves the route passes the
    right action/ids, independent of what `fanout_state` itself does with them
    (that part is `tests/api/test_notification_fanout.py`'s job)."""
    with patch(
        "app.api.routes.notifications.fanout_state", new_callable=AsyncMock
    ) as mock:
        yield mock


class TestFanoutWiring:
    """One test per state-changing route: it must call `fanout_state` with
    the action/ids pair from the table in `_notification_fanout.py`."""

    def test_mark_read_sends_read(
        self, client, auth_headers, db_session, test_user, mock_fanout
    ):
        n = _notification(test_user.id)
        db_session.add(n)
        db_session.commit()

        resp = client.post(f"/api/notifications/{n.id}/read", headers=auth_headers)

        assert resp.status_code == 200
        mock_fanout.assert_awaited_once()
        args, kwargs = mock_fanout.call_args
        assert args[1] == test_user.id
        assert args[2] == [n.id]
        assert args[3] == "read"
        assert kwargs == {"is_admin": False}

    def test_mark_all_as_read_sends_read_all(
        self, client, auth_headers, db_session, test_user, mock_fanout
    ):
        db_session.add(_notification(test_user.id))
        db_session.commit()

        resp = client.post("/api/notifications/read-all", headers=auth_headers)

        assert resp.status_code == 200
        mock_fanout.assert_awaited_once()
        args, kwargs = mock_fanout.call_args
        assert args[1] == test_user.id
        assert args[2] == []
        assert args[3] == "read_all"
        assert kwargs == {"is_admin": False}

    def test_mark_all_as_read_skips_fanout_when_nothing_to_do(
        self, client, auth_headers, mock_fanout
    ):
        """The `if count:` guard: no unread notifications -> no fan-out."""
        resp = client.post("/api/notifications/read-all", headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json()["count"] == 0
        mock_fanout.assert_not_awaited()

    def test_dismiss_all_sends_dismissed_all(
        self, client, auth_headers, db_session, test_user, mock_fanout
    ):
        db_session.add(_notification(test_user.id))
        db_session.commit()

        resp = client.post("/api/notifications/dismiss-all", headers=auth_headers)

        assert resp.status_code == 200
        mock_fanout.assert_awaited_once()
        args, kwargs = mock_fanout.call_args
        assert args[1] == test_user.id
        assert args[2] == []
        assert args[3] == "dismissed_all"
        assert kwargs == {"is_admin": False}

    def test_dismiss_all_skips_fanout_when_nothing_to_do(
        self, client, auth_headers, mock_fanout
    ):
        """The `if count:` guard: no active notifications -> no fan-out."""
        resp = client.post("/api/notifications/dismiss-all", headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json()["count"] == 0
        mock_fanout.assert_not_awaited()

    def test_dismiss_sends_dismissed(
        self, client, auth_headers, db_session, test_user, mock_fanout
    ):
        n = _notification(test_user.id)
        db_session.add(n)
        db_session.commit()

        resp = client.post(f"/api/notifications/{n.id}/dismiss", headers=auth_headers)

        assert resp.status_code == 200
        mock_fanout.assert_awaited_once()
        args, kwargs = mock_fanout.call_args
        assert args[1] == test_user.id
        assert args[2] == [n.id]
        assert args[3] == "dismissed"
        assert kwargs == {"is_admin": False}

    def test_snooze_sends_snoozed(
        self, client, auth_headers, db_session, test_user, mock_fanout
    ):
        n = _notification(test_user.id)
        db_session.add(n)
        db_session.commit()

        resp = client.post(
            f"/api/notifications/{n.id}/snooze",
            params={"duration_hours": 1},
            headers=auth_headers,
        )

        assert resp.status_code == 200
        mock_fanout.assert_awaited_once()
        args, kwargs = mock_fanout.call_args
        assert args[1] == test_user.id
        assert args[2] == [n.id]
        assert args[3] == "snoozed"
        assert kwargs == {"is_admin": False}

    def test_restore_sends_restored(
        self, client, auth_headers, db_session, test_user, mock_fanout
    ):
        n = _notification(test_user.id, trashed=True)
        db_session.add(n)
        db_session.commit()

        resp = client.post(f"/api/notifications/{n.id}/restore", headers=auth_headers)

        assert resp.status_code == 200
        mock_fanout.assert_awaited_once()
        args, kwargs = mock_fanout.call_args
        assert args[1] == test_user.id
        assert args[2] == [n.id]
        assert args[3] == "restored"
        assert kwargs == {"is_admin": False}

    def test_empty_trash_sends_deleted_all(
        self, client, auth_headers, db_session, test_user, mock_fanout
    ):
        db_session.add(_notification(test_user.id, trashed=True))
        db_session.commit()

        resp = client.delete("/api/notifications/trash", headers=auth_headers)

        assert resp.status_code == 200
        mock_fanout.assert_awaited_once()
        args, kwargs = mock_fanout.call_args
        assert args[1] == test_user.id
        assert args[2] == []
        assert args[3] == "deleted_all"
        assert kwargs == {"is_admin": False}

    def test_empty_trash_skips_fanout_when_nothing_to_do(
        self, client, auth_headers, mock_fanout
    ):
        """The `if count:` guard: nothing trashed -> no fan-out."""
        resp = client.delete("/api/notifications/trash", headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json()["count"] == 0
        mock_fanout.assert_not_awaited()

    def test_delete_sends_deleted(
        self, client, auth_headers, db_session, test_user, mock_fanout
    ):
        n = _notification(test_user.id)
        db_session.add(n)
        db_session.commit()
        nid = n.id

        resp = client.delete(f"/api/notifications/{nid}", headers=auth_headers)

        assert resp.status_code == 204
        mock_fanout.assert_awaited_once()
        args, kwargs = mock_fanout.call_args
        assert args[1] == test_user.id
        assert args[2] == [nid]
        assert args[3] == "deleted"
        assert kwargs == {"is_admin": False}
