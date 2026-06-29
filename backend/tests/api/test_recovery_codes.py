"""Recovery-code management endpoints (generate with step-up, status)."""
import pyotp

from app.core.config import settings

PREFIX = settings.api_prefix
# user_headers logs in as testuser / Testpass123! (conftest)
USER_PW = "Testpass123!"


class TestRecoveryCodeManagement:
    def test_status_unconfigured_then_generate_with_password_stepup(self, client, user_headers):
        s = client.get(f"{PREFIX}/auth/recovery-codes/status", headers=user_headers)
        assert s.status_code == 200
        assert s.json() == {"configured": False, "remaining": 0}

        # testuser has no 2FA → step-up is current_password
        g = client.post(f"{PREFIX}/auth/recovery-codes",
                        json={"current_password": USER_PW}, headers=user_headers)
        assert g.status_code == 200
        assert len(g.json()["recovery_codes"]) == 10

        s2 = client.get(f"{PREFIX}/auth/recovery-codes/status", headers=user_headers)
        assert s2.json() == {"configured": True, "remaining": 10}

    def test_generate_wrong_password_denied(self, client, user_headers):
        g = client.post(f"{PREFIX}/auth/recovery-codes",
                        json={"current_password": "WrongPass9x"}, headers=user_headers)
        assert g.status_code == 401

    def test_generate_requires_auth(self, client):
        assert client.post(f"{PREFIX}/auth/recovery-codes", json={}).status_code == 401

    def test_totp_stepup_required_and_succeeds(self, client, user_headers):
        """TOTP-enabled user must provide a valid TOTP code, not a password, to generate codes."""
        # Enable 2FA for testuser via the API (mirrors test_2fa_endpoints.py patterns).
        setup_resp = client.post(f"{PREFIX}/auth/2fa/setup", headers=user_headers)
        assert setup_resp.status_code == 200
        secret = setup_resp.json()["secret"]
        totp = pyotp.TOTP(secret)
        verify_resp = client.post(
            f"{PREFIX}/auth/2fa/verify-setup",
            json={"secret": secret, "code": totp.now()},
            headers=user_headers,
        )
        assert verify_resp.status_code == 200

        # (a) Wrong TOTP code → step-up fails → 401.
        bad = client.post(f"{PREFIX}/auth/recovery-codes",
                          json={"code": "000000"}, headers=user_headers)
        assert bad.status_code == 401

        # (b) Fresh valid TOTP code → 200 + exactly 10 codes.
        good = client.post(f"{PREFIX}/auth/recovery-codes",
                           json={"code": totp.now()}, headers=user_headers)
        assert good.status_code == 200
        assert len(good.json()["recovery_codes"]) == 10


import pytest


@pytest.fixture
def disabled_reset_user(db_session):
    """A user with recovery codes generated but whose account is disabled (is_active=False)."""
    from app.services import users as user_service
    from app.schemas.user import UserCreate
    from app.services import recovery_code_service
    u = user_service.create_user(
        UserCreate(username="disableduser", email="disabled@example.com", password="OldPass123x", role="user"),
        db=db_session,
    )
    codes = recovery_code_service.generate_recovery_codes(db_session, u.id)
    u.is_active = False
    db_session.commit()
    return u, codes


@pytest.fixture
def reset_user(db_session):
    from app.services import users as user_service
    from app.schemas.user import UserCreate
    from app.services import recovery_code_service
    u = user_service.create_user(
        UserCreate(username="resetme", email="reset@example.com", password="OldPass123x", role="user"),
        db=db_session,
    )
    codes = recovery_code_service.generate_recovery_codes(db_session, u.id)
    return u, codes


class TestRecoveryReset:
    # The test client sends host='testclient', which is not a recognised private IP.
    # Patch the bound name in the auth module to True for all tests in this class;
    # test_non_local_forbidden overrides it to False via its own monkeypatch call.
    @pytest.fixture(autouse=True)
    def _patch_local_ip(self, monkeypatch):
        import app.api.routes.auth as auth_routes
        monkeypatch.setattr(auth_routes, "is_private_or_local_ip", lambda ip: True)

    def test_happy_path_no_token_and_login_works(self, client, reset_user, db_session):
        u, codes = reset_user
        r = client.post(f"{PREFIX}/auth/recovery-reset", json={
            "username": "resetme", "recovery_code": codes[0], "new_password": "BrandNew9xPass",
        })
        assert r.status_code == 200, r.text
        assert "access_token" not in r.json()
        login = client.post(f"{PREFIX}/auth/login", json={"username": "resetme", "password": "BrandNew9xPass"})
        assert login.status_code == 200

    def test_revokes_existing_refresh_tokens(self, client, reset_user, db_session):
        u, codes = reset_user
        from app.services.token_service import token_service
        # seed an active refresh token
        from datetime import datetime, timezone, timedelta
        token_service.store_refresh_token(
            db_session, jti="jti-test", user_id=u.id, token="rawtok",
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        client.post(f"{PREFIX}/auth/recovery-reset", json={
            "username": "resetme", "recovery_code": codes[0], "new_password": "BrandNew9xPass",
        })
        assert token_service.is_token_revoked(db_session, "jti-test") is True

    def test_wrong_code_generic(self, client, reset_user):
        r = client.post(f"{PREFIX}/auth/recovery-reset", json={
            "username": "resetme", "recovery_code": "WRONGCODE0", "new_password": "BrandNew9xPass",
        })
        assert r.status_code == 401
        assert r.json()["detail"] == "Invalid username or recovery code"

    def test_unknown_user_same_generic(self, client):
        r = client.post(f"{PREFIX}/auth/recovery-reset", json={
            "username": "ghost", "recovery_code": "ABCD123456", "new_password": "BrandNew9xPass",
        })
        assert r.status_code == 401
        assert r.json()["detail"] == "Invalid username or recovery code"

    def test_weak_password_422_does_not_consume(self, client, reset_user):
        u, codes = reset_user
        bad = client.post(f"{PREFIX}/auth/recovery-reset", json={
            "username": "resetme", "recovery_code": codes[0], "new_password": "weak",
        })
        assert bad.status_code == 422
        good = client.post(f"{PREFIX}/auth/recovery-reset", json={
            "username": "resetme", "recovery_code": codes[0], "new_password": "BrandNew9xPass",
        })
        assert good.status_code == 200

    def test_non_local_forbidden(self, client, reset_user, monkeypatch):
        u, codes = reset_user
        import app.api.routes.auth as auth_routes
        monkeypatch.setattr(auth_routes, "is_private_or_local_ip", lambda ip: False)
        r = client.post(f"{PREFIX}/auth/recovery-reset", json={
            "username": "resetme", "recovery_code": codes[0], "new_password": "BrandNew9xPass",
        })
        assert r.status_code == 403
        assert r.json()["detail"]["error"] == "local_network_required"

    def test_audit_rows_written(self, client, reset_user, db_session):
        u, codes = reset_user
        client.post(f"{PREFIX}/auth/recovery-reset", json={
            "username": "resetme", "recovery_code": codes[0], "new_password": "BrandNew9xPass",
        })
        from app.models import AuditLog
        row = db_session.query(AuditLog).filter(AuditLog.action == "password_reset_via_recovery").first()
        assert row is not None

    def test_disabled_user_reset_generic_401(self, client, disabled_reset_user):
        """A disabled (is_active=False) user with valid recovery codes must receive the same
        generic 401 as an unknown/wrong-code attempt (anti-enumeration invariant)."""
        u, codes = disabled_reset_user
        r = client.post(f"{PREFIX}/auth/recovery-reset", json={
            "username": "disableduser", "recovery_code": codes[0], "new_password": "BrandNew9xPass",
        })
        assert r.status_code == 401
        assert r.json()["detail"] == "Invalid username or recovery code"
