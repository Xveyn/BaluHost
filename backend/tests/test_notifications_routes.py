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
