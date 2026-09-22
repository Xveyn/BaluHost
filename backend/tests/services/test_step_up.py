"""Tests für den zweiten Nachweis vor privilegierten Aktionen."""
from types import SimpleNamespace

import pytest

from app.services import step_up


@pytest.fixture
def password_user():
    return SimpleNamespace(id=1, username="admin", totp_enabled=False)


@pytest.fixture
def totp_user():
    return SimpleNamespace(id=2, username="admin2fa", totp_enabled=True)


def test_password_accepted(monkeypatch, password_user):
    monkeypatch.setattr(
        "app.services.auth.authenticate_user",
        lambda username, password, db=None: password_user if password == "richtig" else None,
    )
    assert step_up.verify_step_up(None, password_user, "richtig", None) is True


def test_wrong_password_rejected(monkeypatch, password_user):
    monkeypatch.setattr(
        "app.services.auth.authenticate_user",
        lambda username, password, db=None: None,
    )
    assert step_up.verify_step_up(None, password_user, "falsch", None) is False


def test_missing_password_rejected(password_user):
    """Kein Feld gesetzt ist ein gescheiterter Nachweis, kein Sonderfall."""
    assert step_up.verify_step_up(None, password_user, None, None) is False


def test_totp_user_ignores_password(monkeypatch, totp_user):
    """Mit 2FA zählt nur der Code — ein Passwort öffnet nichts."""
    monkeypatch.setattr(
        "app.services.auth.authenticate_user",
        lambda username, password, db=None: totp_user,
    )
    assert step_up.verify_step_up(None, totp_user, "richtig", None) is False


def test_totp_code_accepted(monkeypatch, totp_user):
    monkeypatch.setattr(
        "app.services.totp_service.verify_code",
        lambda db, user_id, code: code == "123456",
    )
    assert step_up.verify_step_up(None, totp_user, None, "123456") is True


def test_backup_code_accepted_when_totp_fails(monkeypatch, totp_user):
    monkeypatch.setattr(
        "app.services.totp_service.verify_code",
        lambda db, user_id, code: False,
    )
    monkeypatch.setattr(
        "app.services.totp_service.verify_backup_code",
        lambda db, user_id, code: code == "backup-1",
    )
    assert step_up.verify_step_up(None, totp_user, None, "backup-1") is True


def test_value_error_from_totp_is_a_rejection(monkeypatch, totp_user):
    """verify_code wirft ValueError, wenn kein Secret hinterlegt ist."""
    def boom(db, user_id, code):
        raise ValueError("no secret")

    monkeypatch.setattr("app.services.totp_service.verify_code", boom)
    monkeypatch.setattr("app.services.totp_service.verify_backup_code", boom)
    assert step_up.verify_step_up(None, totp_user, None, "123456") is False
