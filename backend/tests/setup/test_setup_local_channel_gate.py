"""Tests verifying the setup wizard uses the local-channel gate."""
import pytest
from app.core.config import settings


def test_setup_admin_blocked_on_remote_without_secret(remote_client, monkeypatch, db_session):
    monkeypatch.setattr(settings, "setup_secret", "")
    # Ensure no users exist (setup-required state)
    from app.models.user import User
    db_session.query(User).delete()
    db_session.commit()

    resp = remote_client.post(
        "/api/setup/admin",
        json={"username": "admin2", "password": "Strong123!"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"] == "local_channel_required"


def test_setup_admin_passes_on_local(client, monkeypatch, db_session):
    """Default channel in test suite is 'local' — endpoint passes."""
    monkeypatch.setattr(settings, "setup_secret", "")
    from app.models.user import User
    db_session.query(User).delete()
    db_session.commit()

    resp = client.post(
        "/api/setup/admin",
        json={"username": "admin2", "password": "Strong123!"},
    )
    assert resp.status_code == 201


def test_setup_admin_passes_on_remote_with_secret(remote_client, monkeypatch, db_session):
    monkeypatch.setattr(settings, "setup_secret", "ansible-go")
    from app.models.user import User
    db_session.query(User).delete()
    db_session.commit()

    resp = remote_client.post(
        "/api/setup/admin",
        json={
            "username": "admin2",
            "password": "Strong123!",
            "setup_secret": "ansible-go",
        },
    )
    assert resp.status_code == 201
