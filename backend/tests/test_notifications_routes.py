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

    def test_delete_permanently_removes_row(
        self, client, auth_headers, db_session, test_user
    ):
        from app.models.notification import Notification

        n = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="t",
            message="m",
        )
        db_session.add(n)
        db_session.commit()
        nid = n.id

        resp = client.delete(
            f"/api/notifications/{nid}", headers=auth_headers
        )
        assert resp.status_code == 204
        assert (
            db_session.query(Notification)
            .filter(Notification.id == nid)
            .first()
            is None
        )

    def test_delete_unknown_id_returns_404(
        self, client, auth_headers
    ):
        resp = client.delete(
            "/api/notifications/99999999", headers=auth_headers
        )
        assert resp.status_code == 404

    def test_empty_trash_returns_count(
        self, client, auth_headers, db_session, test_user
    ):
        from app.models.notification import Notification

        for i in range(3):
            db_session.add(Notification(
                user_id=test_user.id,
                category="system",
                notification_type="info",
                title=f"t{i}",
                message="m",
                deleted_at=datetime.now(timezone.utc),
            ))
        db_session.commit()

        resp = client.delete("/api/notifications/trash", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == {"count": 3}
        assert db_session.query(Notification).filter(
            Notification.user_id == test_user.id,
            Notification.deleted_at.is_not(None),
        ).count() == 0

    def test_trash_retention_validation_rejects_out_of_range(
        self, client, auth_headers
    ):
        # 0 → 422
        resp = client.put(
            "/api/notifications/preferences",
            headers=auth_headers,
            json={"trash_retention_days": 0},
        )
        assert resp.status_code == 422
        # 8 → 422
        resp = client.put(
            "/api/notifications/preferences",
            headers=auth_headers,
            json={"trash_retention_days": 8},
        )
        assert resp.status_code == 422

    def test_trash_retention_persists_via_preferences_endpoint(
        self, client, auth_headers
    ):
        # PUT 3 → 200, then GET returns 3
        resp = client.put(
            "/api/notifications/preferences",
            headers=auth_headers,
            json={"trash_retention_days": 3},
        )
        assert resp.status_code == 200
        get_resp = client.get(
            "/api/notifications/preferences", headers=auth_headers
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["trash_retention_days"] == 3


class TestUpdatedAfterQuery:
    """#504 problem 2, end to end.

    Fix round 1: the first draft of this class never inserted a Notification,
    so two of the four tests were trivially green against an empty DB — a
    reviewer reverted the route's `updated_after` parameter and the same two
    tests still passed. Every test that asserts on content now creates its
    own row(s) first. Backdating follows the same no-sleep technique as
    `TestUpdatedAtSemantics` in `tests/services/test_notification_service.py`:
    `Query.update({...})` on `updated_at` in a separate statement.
    """

    def test_inbox_accepts_updated_after(self, client, auth_headers):
        response = client.get(
            "/api/notifications",
            params={"updated_after": "2020-01-01T00:00:00Z"},
            headers=auth_headers,
        )

        assert response.status_code == 200

    def test_trash_accepts_updated_after(self, client, auth_headers):
        response = client.get(
            "/api/notifications/trash",
            params={"updated_after": "2020-01-01T00:00:00Z"},
            headers=auth_headers,
        )

        assert response.status_code == 200

    def test_every_item_carries_the_stamp(
        self, client, auth_headers, db_session, test_user
    ):
        from app.models.notification import Notification

        db_session.add(Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="t",
            message="m",
        ))
        db_session.commit()

        response = client.get("/api/notifications", headers=auth_headers)

        assert response.status_code == 200
        items = response.json()["notifications"]
        assert items  # non-empty, or the loop below checks nothing
        for item in items:
            assert item["updated_at"] is not None

    def test_a_far_future_cutoff_returns_nothing(
        self, client, auth_headers, db_session, test_user
    ):
        """Guards against the parameter being silently ignored — a filter that
        does nothing would let the client think it is fully synced."""
        from app.models.notification import Notification

        db_session.add(Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="t",
            message="m",
        ))
        db_session.commit()

        # Baseline: without the filter the row is there, so the cutoff below
        # is provably doing something rather than hitting an empty table.
        baseline = client.get("/api/notifications", headers=auth_headers)
        assert baseline.status_code == 200
        assert baseline.json()["notifications"] != []

        response = client.get(
            "/api/notifications",
            params={"updated_after": "2999-01-01T00:00:00Z"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["notifications"] == []

    def test_window_includes_recent_and_excludes_backdated(
        self, client, auth_headers, db_session, test_user
    ):
        """Both directions in one run: a row inside the window comes back, a
        row backdated to before it does not."""
        from app.models.notification import Notification

        recent = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="recent",
            message="m",
        )
        old = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="old",
            message="m",
        )
        db_session.add_all([recent, old])
        db_session.commit()

        db_session.query(Notification).filter_by(id=old.id).update(
            {Notification.updated_at: datetime(2020, 1, 1, tzinfo=timezone.utc)},
            synchronize_session=False,
        )
        db_session.commit()

        response = client.get(
            "/api/notifications",
            params={"updated_after": "2025-01-01T00:00:00Z"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        titles = [n["title"] for n in response.json()["notifications"]]
        assert titles == ["recent"]
