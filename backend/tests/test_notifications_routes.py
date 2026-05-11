"""Integration tests for notification routes."""
from datetime import datetime, timezone


class TestTrashRoutes:
    """Tests for trash-specific route endpoints."""

    def test_get_trash_returns_only_trashed(
        self, client, auth_headers, db_session, test_user
    ):
        from app.models.notification import Notification

        active = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="active",
            message="m",
        )
        trashed = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="trashed",
            message="m",
            deleted_at=datetime.now(timezone.utc),
        )
        db_session.add_all([active, trashed])
        db_session.commit()

        resp = client.get("/api/notifications/trash", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        titles = [n["title"] for n in data["notifications"]]
        assert titles == ["trashed"]

    def test_restore_round_trip(
        self, client, auth_headers, db_session, test_user
    ):
        from app.models.notification import Notification

        n = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="t",
            message="m",
            deleted_at=datetime.now(timezone.utc),
        )
        db_session.add(n)
        db_session.commit()

        resp = client.post(
            f"/api/notifications/{n.id}/restore", headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.json()["deleted_at"] is None

    def test_restore_unknown_id_returns_404(
        self, client, auth_headers
    ):
        resp = client.post(
            "/api/notifications/99999999/restore", headers=auth_headers
        )
        assert resp.status_code == 404
