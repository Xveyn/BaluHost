"""Tests for services/token_service.py — RefreshToken CRUD and revocation."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.models.user import User
from app.services.token_service import TokenService


def _make_jti() -> str:
    return str(uuid.uuid4())


def _future(hours: int = 24) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)


def _past(days: int = 10) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def _store_token(db: Session, user_id: int, **kwargs) -> str:
    """Helper that stores a token and returns the jti."""
    jti = kwargs.pop("jti", _make_jti())
    TokenService.store_refresh_token(
        db,
        jti=jti,
        user_id=user_id,
        token=f"token-{jti}",
        expires_at=kwargs.pop("expires_at", _future()),
        **kwargs,
    )
    return jti


class TestStoreRefreshToken:
    def test_stores_and_retrieves(self, db_session: Session, regular_user: User):
        jti = _make_jti()
        token = TokenService.store_refresh_token(
            db_session,
            jti=jti,
            user_id=regular_user.id,
            token="my-secret-token",
            expires_at=_future(),
            device_id="phone-1",
            ip_address="127.0.0.1",
            user_agent="TestAgent/1.0",
        )
        assert token.jti == jti
        assert token.user_id == regular_user.id
        assert token.revoked is False
        assert token.device_id == "phone-1"
        assert token.created_ip == "127.0.0.1"

    def test_token_hash_not_plaintext(self, db_session: Session, regular_user: User):
        jti = _make_jti()
        token = TokenService.store_refresh_token(
            db_session,
            jti=jti,
            user_id=regular_user.id,
            token="plaintext-value",
            expires_at=_future(),
        )
        assert token.token_hash != "plaintext-value"
        assert len(token.token_hash) == 64  # SHA-256 hex


class TestGetTokenByJti:
    def test_returns_none_for_unknown(self, db_session: Session):
        assert TokenService.get_token_by_jti(db_session, "no-such-jti") is None

    def test_returns_token(self, db_session: Session, regular_user: User):
        jti = _store_token(db_session, regular_user.id)
        found = TokenService.get_token_by_jti(db_session, jti)
        assert found is not None
        assert found.jti == jti


class TestIsTokenRevoked:
    def test_unknown_token_is_revoked(self, db_session: Session):
        assert TokenService.is_token_revoked(db_session, "unknown") is True

    def test_valid_token_not_revoked(self, db_session: Session, regular_user: User):
        jti = _store_token(db_session, regular_user.id)
        assert TokenService.is_token_revoked(db_session, jti) is False

    def test_revoked_token_is_revoked(self, db_session: Session, regular_user: User):
        jti = _store_token(db_session, regular_user.id)
        TokenService.revoke_token(db_session, jti)
        assert TokenService.is_token_revoked(db_session, jti) is True

    def test_expired_token_is_revoked(self, db_session: Session, regular_user: User):
        jti = _store_token(db_session, regular_user.id, expires_at=_past())
        assert TokenService.is_token_revoked(db_session, jti) is True


class TestRevokeToken:
    def test_revokes_existing_token(self, db_session: Session, regular_user: User):
        jti = _store_token(db_session, regular_user.id)
        assert TokenService.revoke_token(db_session, jti, reason="logout") is True

        token = TokenService.get_token_by_jti(db_session, jti)
        assert token.revoked is True
        assert token.revocation_reason == "logout"

    def test_returns_false_for_unknown(self, db_session: Session):
        assert TokenService.revoke_token(db_session, "unknown") is False


class TestRevokeAllUserTokens:
    def test_revokes_all_active_tokens(self, db_session: Session, regular_user: User):
        jti1 = _store_token(db_session, regular_user.id)
        jti2 = _store_token(db_session, regular_user.id)

        count = TokenService.revoke_all_user_tokens(
            db_session, regular_user.id, reason="password_change"
        )
        assert count == 2

        assert TokenService.is_token_revoked(db_session, jti1) is True
        assert TokenService.is_token_revoked(db_session, jti2) is True

    def test_returns_zero_when_no_tokens(self, db_session: Session, regular_user: User):
        assert TokenService.revoke_all_user_tokens(db_session, regular_user.id) == 0

    def test_does_not_double_revoke(self, db_session: Session, regular_user: User):
        jti = _store_token(db_session, regular_user.id)
        TokenService.revoke_token(db_session, jti)
        # Already revoked, should not be counted again
        count = TokenService.revoke_all_user_tokens(db_session, regular_user.id)
        assert count == 0


class TestRevokeDeviceTokens:
    def test_revokes_by_device(self, db_session: Session, regular_user: User):
        _store_token(db_session, regular_user.id, device_id="device-A")
        _store_token(db_session, regular_user.id, device_id="device-A")
        _store_token(db_session, regular_user.id, device_id="device-B")

        count = TokenService.revoke_device_tokens(db_session, "device-A")
        assert count == 2

    def test_returns_zero_for_unknown_device(self, db_session: Session):
        assert TokenService.revoke_device_tokens(db_session, "no-device") == 0


class TestUpdateTokenUsage:
    def test_updates_timestamp_and_ip(self, db_session: Session, regular_user: User):
        jti = _store_token(db_session, regular_user.id)
        assert TokenService.update_token_usage(db_session, jti, ip_address="10.0.0.1") is True

        token = TokenService.get_token_by_jti(db_session, jti)
        assert token.last_used_at is not None
        assert token.last_used_ip == "10.0.0.1"

    def test_updates_without_ip(self, db_session: Session, regular_user: User):
        jti = _store_token(db_session, regular_user.id)
        assert TokenService.update_token_usage(db_session, jti) is True

    def test_returns_false_for_unknown(self, db_session: Session):
        assert TokenService.update_token_usage(db_session, "nope") is False


class TestCleanupExpiredTokens:
    def test_deletes_old_expired_tokens(self, db_session: Session, regular_user: User):
        # Expired 10 days ago — beyond the 7-day cutoff
        _store_token(db_session, regular_user.id, expires_at=_past(days=10))
        # Still valid
        jti_valid = _store_token(db_session, regular_user.id, expires_at=_future())

        deleted = TokenService.cleanup_expired_tokens(db_session)
        assert deleted == 1
        # Valid token should still exist
        assert TokenService.get_token_by_jti(db_session, jti_valid) is not None

    def test_keeps_recently_expired_tokens(self, db_session: Session, regular_user: User):
        # Expired 2 days ago — within 7-day grace period
        _store_token(
            db_session,
            regular_user.id,
            expires_at=datetime.now(timezone.utc) - timedelta(days=2),
        )
        deleted = TokenService.cleanup_expired_tokens(db_session)
        assert deleted == 0


class TestGetUserActiveTokens:
    def test_returns_active_tokens(self, db_session: Session, regular_user: User):
        _store_token(db_session, regular_user.id)
        _store_token(db_session, regular_user.id)

        tokens = TokenService.get_user_active_tokens(db_session, regular_user.id)
        assert len(tokens) == 2

    def test_excludes_revoked(self, db_session: Session, regular_user: User):
        jti = _store_token(db_session, regular_user.id)
        _store_token(db_session, regular_user.id)
        TokenService.revoke_token(db_session, jti)

        tokens = TokenService.get_user_active_tokens(db_session, regular_user.id)
        assert len(tokens) == 1

    def test_excludes_expired(self, db_session: Session, regular_user: User):
        _store_token(db_session, regular_user.id, expires_at=_past())
        _store_token(db_session, regular_user.id, expires_at=_future())

        tokens = TokenService.get_user_active_tokens(db_session, regular_user.id)
        assert len(tokens) == 1


class TestVerifyTokenOwnership:
    def test_returns_true_for_owner(self, db_session: Session, regular_user: User):
        jti = _store_token(db_session, regular_user.id)
        assert TokenService.verify_token_ownership(db_session, jti, regular_user.id) is True

    def test_returns_false_for_wrong_user(self, db_session: Session, regular_user: User):
        jti = _store_token(db_session, regular_user.id)
        assert TokenService.verify_token_ownership(db_session, jti, 99999) is False

    def test_returns_false_for_unknown_token(self, db_session: Session):
        assert TokenService.verify_token_ownership(db_session, "unknown", 1) is False
