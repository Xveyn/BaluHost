"""Plugin-derived notification categories must survive the REST read path.

Since subproject 3 of the Steam track (#463) the core derives a plugin event's
category from the PLUGIN NAME - deliberately, so a plugin cannot widen its own
delivery reach by choosing a routing key. That makes the category an OPEN set at
runtime.

NotificationResponse.category used to be a closed Literal of the nine core
categories. The first plugin notification ever persisted therefore turned every
read endpoint into a 500 - and because the list endpoint fails as a whole, that
ONE row hid every other notification with it. Observed in production on
2026-07-24 (GET /api/notifications and POST /api/notifications/{id}/read).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.notification import Notification

PLUGIN_CATEGORY = "steam_gaming"


@pytest.fixture
def plugin_notification(db_session, admin_user) -> Notification:
    """A notification exactly as emit_plugin_event() persists one."""
    row = Notification(
        user_id=admin_user.id,
        notification_type="info",
        category=PLUGIN_CATEGORY,
        title="Gaming-Session beendet",
        message="Metro Exodus Enhanced Edition wurde beendet.",
        action_url="/plugins",
        priority=0,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


class TestPluginCategorySurvivesTheReadPath:
    def test_list_returns_the_plugin_notification(
        self, client, admin_headers, plugin_notification
    ):
        response = client.get("/api/notifications", headers=admin_headers)

        assert response.status_code == 200, response.text
        categories = [n["category"] for n in response.json()["notifications"]]
        assert PLUGIN_CATEGORY in categories

    def test_one_plugin_row_does_not_hide_the_core_notifications(
        self, client, admin_headers, db_session, admin_user, plugin_notification
    ):
        """The 500 was on the whole list, so a single plugin row buried
        everything else - that is what made this a total outage of the page."""
        db_session.add(
            Notification(
                user_id=admin_user.id,
                notification_type="warning",
                category="raid",
                title="RAID degraded",
                message="md1 is degraded.",
                priority=2,
            )
        )
        db_session.commit()

        response = client.get("/api/notifications", headers=admin_headers)

        assert response.status_code == 200, response.text
        categories = [n["category"] for n in response.json()["notifications"]]
        assert "raid" in categories
        assert PLUGIN_CATEGORY in categories

    def test_mark_read_returns_the_plugin_notification(
        self, client, admin_headers, plugin_notification
    ):
        """Without this the user cannot even dismiss the notification that
        breaks the page."""
        response = client.post(
            f"/api/notifications/{plugin_notification.id}/read", headers=admin_headers
        )

        assert response.status_code == 200, response.text
        assert response.json()["category"] == PLUGIN_CATEGORY

    def test_filtering_by_a_plugin_category_is_accepted(
        self, client, admin_headers, plugin_notification
    ):
        """A closed Literal on the query parameter would 422 here, so plugin
        notifications could never be filtered for."""
        response = client.get(
            "/api/notifications",
            params={"category": PLUGIN_CATEGORY},
            headers=admin_headers,
        )

        assert response.status_code == 200, response.text
        categories = {n["category"] for n in response.json()["notifications"]}
        assert categories == {PLUGIN_CATEGORY}

    def test_trash_returns_the_plugin_notification(
        self, client, admin_headers, db_session, plugin_notification
    ):
        plugin_notification.deleted_at = datetime.now(timezone.utc)
        db_session.commit()

        response = client.get("/api/notifications/trash", headers=admin_headers)

        assert response.status_code == 200, response.text
        categories = [n["category"] for n in response.json()["notifications"]]
        assert PLUGIN_CATEGORY in categories


class TestCoreCategoriesAreUnaffected:
    def test_a_core_category_still_round_trips(
        self, client, admin_headers, db_session, admin_user
    ):
        db_session.add(
            Notification(
                user_id=admin_user.id,
                notification_type="critical",
                category="security",
                title="Failed logins",
                message="5 failed logins.",
                priority=3,
            )
        )
        db_session.commit()

        response = client.get("/api/notifications", headers=admin_headers)

        assert response.status_code == 200, response.text
        assert "security" in [n["category"] for n in response.json()["notifications"]]
