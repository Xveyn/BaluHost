"""Tests for notification routing feature."""

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.notification_routing import UserNotificationRouting
from app.schemas.notification_routing import NotificationRoutingUpdate


class TestNotificationRoutingModel:
    """Tests for the UserNotificationRouting model."""

    def test_create_routing(self, db, admin_user):
        """New routing row has all categories disabled by default."""
        routing = UserNotificationRouting(user_id=admin_user.id)
        db.add(routing)
        db.commit()
        db.refresh(routing)

        assert routing.receive_raid is False
        assert routing.receive_smart is False
        assert routing.receive_backup is False
        assert routing.receive_scheduler is False
        assert routing.receive_system is False
        assert routing.receive_security is False
        assert routing.receive_sync is False
        assert routing.receive_vpn is False

    def test_unique_user_id(self, db, regular_user):
        """Only one routing row per user."""
        db.add(UserNotificationRouting(user_id=regular_user.id))
        db.commit()
        db.add(UserNotificationRouting(user_id=regular_user.id))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


class TestNotificationRoutingService:
    """Tests for the notification routing service."""

    def test_get_routing_no_row(self, db, regular_user):
        """Returns defaults when no row exists for the user."""
        from app.services.notification_routing import get_routing

        result = get_routing(db, user_id=regular_user.id)
        assert result.user_id == regular_user.id
        assert result.receive_raid is False
        assert result.granted_by is None

    def test_update_routing_creates_row(self, db, admin_user, regular_user):
        """Update creates a new row if none exists."""
        from app.services.notification_routing import update_routing

        update = NotificationRoutingUpdate(receive_raid=True, receive_security=True)
        result = update_routing(
            db, user_id=regular_user.id, update=update, granted_by=admin_user.id
        )

        assert result.receive_raid is True
        assert result.receive_security is True
        assert result.receive_smart is False
        assert result.granted_by == admin_user.id

    def test_update_routing_partial(self, db, admin_user, regular_user):
        """Partial update only changes specified fields, leaving others intact."""
        from app.services.notification_routing import update_routing

        # Create with raid=True
        update1 = NotificationRoutingUpdate(receive_raid=True)
        update_routing(db, user_id=regular_user.id, update=update1, granted_by=admin_user.id)

        # Update only smart; raid should remain True
        update2 = NotificationRoutingUpdate(receive_smart=True)
        result = update_routing(
            db, user_id=regular_user.id, update=update2, granted_by=admin_user.id
        )

        assert result.receive_raid is True
        assert result.receive_smart is True

    def test_check_routing(self, db, admin_user, regular_user):
        """check_routing returns the correct boolean for each category."""
        from app.services.notification_routing import check_routing, update_routing

        update = NotificationRoutingUpdate(receive_raid=True)
        update_routing(db, user_id=regular_user.id, update=update, granted_by=admin_user.id)

        assert check_routing(db, regular_user.id, "raid") is True
        assert check_routing(db, regular_user.id, "smart") is False
        assert check_routing(db, regular_user.id, "nonexistent") is False

    def test_get_routed_user_ids(self, db, admin_user, regular_user):
        """get_routed_user_ids returns only non-admin users with routing enabled."""
        from app.services.notification_routing import get_routed_user_ids, update_routing

        # Give regular user raid routing
        update = NotificationRoutingUpdate(receive_raid=True)
        update_routing(db, user_id=regular_user.id, update=update, granted_by=admin_user.id)

        routed = get_routed_user_ids(db, "raid")
        assert regular_user.id in routed
        # Admin should not appear even if they happen to have a routing row
        assert admin_user.id not in routed

        # A category with no routing enabled should return empty
        assert get_routed_user_ids(db, "smart") == []


class TestNotificationRoutingAPI:
    """Tests for notification routing API endpoints."""

    def test_get_routing_requires_admin(self, client, user_headers, regular_user):
        """Non-admin cannot read another user's routing via the admin endpoint."""
        resp = client.get(
            f"/api/users/{regular_user.id}/notification-routing",
            headers=user_headers,
        )
        assert resp.status_code in (401, 403)

    def test_get_routing_admin(self, client, admin_headers, regular_user):
        """Admin can read a user's routing; defaults are all False."""
        resp = client.get(
            f"/api/users/{regular_user.id}/notification-routing",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["receive_raid"] is False

    def test_update_routing_admin(self, client, admin_headers, regular_user):
        """Admin can update routing; response reflects new and unchanged values."""
        resp = client.put(
            f"/api/users/{regular_user.id}/notification-routing",
            headers=admin_headers,
            json={"receive_raid": True, "receive_system": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["receive_raid"] is True
        assert data["receive_system"] is True
        assert data["receive_smart"] is False

    def test_my_routing(self, client, user_headers):
        """User can read their own routing via the my-routing endpoint."""
        resp = client.get(
            "/api/notifications/my-routing",
            headers=user_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "receive_raid" in data
        # MyNotificationRoutingResponse should not expose admin metadata
        assert "granted_by" not in data
