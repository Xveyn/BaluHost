"""Every session token must carry the TTL the admin configured.

Five routes in auth.py hand out access tokens. Before this change each one
silently inherited ``settings.ACCESS_TOKEN_EXPIRE_MINUTES``; the production box
had a well-meant ``TOKEN_EXPIRE_MINUTES=720`` in its env file that never
matched a settings field and therefore did nothing for months. The fix is one
issuing helper plus a test that notices when a sixth route bypasses it.
"""
from __future__ import annotations

import re

import jwt as pyjwt
import pytest

from app.core.config import settings

ADMIN_URL = f"{settings.api_prefix}/admin/auth-policy"
LOGIN_URL = f"{settings.api_prefix}/auth/login"


def _ttl_minutes(token: str) -> float:
    """Lifetime the token was actually minted with, from its own claims."""
    claims = pyjwt.decode(
        token, settings.SECRET_KEY, algorithms=["HS256"], options={"verify_exp": False}
    )
    return (claims["exp"] - claims["iat"]) / 60


def _login(client) -> str:
    r = client.post(
        LOGIN_URL,
        json={"username": settings.admin_username, "password": settings.admin_password},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


class TestLoginHonoursThePolicy:
    def test_default_policy_gives_the_documented_fifteen_minutes(
        self, client, admin_user
    ):
        assert _ttl_minutes(_login(client)) == pytest.approx(15, abs=0.2)

    def test_a_raised_policy_reaches_the_token(self, client, admin_headers):
        """The assertion that would have caught the dead env variable."""
        client.put(ADMIN_URL, headers=admin_headers, json={"access_token_minutes": 720})

        assert _ttl_minutes(_login(client)) == pytest.approx(720, abs=0.2)

    def test_registration_issues_the_same_ttl(self, client, admin_headers):
        client.put(ADMIN_URL, headers=admin_headers, json={"access_token_minutes": 90})

        r = client.post(
            f"{settings.api_prefix}/auth/register",
            json={
                "username": "ttluser",
                "email": "ttl@example.com",
                "password": "Testpass123!",
            },
        )

        if r.status_code in (403, 404):
            pytest.skip("registration is closed in this configuration")
        assert r.status_code in (200, 201), r.text
        assert _ttl_minutes(r.json()["access_token"]) == pytest.approx(90, abs=0.2)


class TestNoRouteMintsItsOwnTtl:
    """A structural guard, not a behavioral one.

    Each token route is three lines of boilerplate; the next one will be
    written by copying a neighbour. If that copy calls the auth service
    directly it inherits the config default again and the admin's setting
    silently stops applying to one login path. Cheaper to fail here than to
    debug "only PIN logins expire early" later.
    """

    def test_auth_routes_issue_tokens_only_through_the_helper(self):
        from pathlib import Path

        import app.api.routes.auth as auth_routes

        source = Path(auth_routes.__file__).read_text(encoding="utf-8")

        enclosing = "<module>"
        direct = []
        for line in source.splitlines():
            match = re.match(r"(?:async )?def (\w+)", line)
            if match:
                enclosing = match.group(1)
            if "auth_service.create_access_token(" in line:
                # The helper itself is the one legitimate caller.
                if enclosing != "_issue_session_token":
                    direct.append(f"{enclosing}: {line.strip()}")

        assert direct == [], (
            "these bypass _issue_session_token() and would ignore the "
            f"configured token TTL: {direct}"
        )

    def test_the_helper_actually_reads_the_policy(self, db_session):
        """Guard against the guard: a helper that ignores the policy would keep
        the scan test green while changing nothing."""
        from app.api.routes import auth as auth_routes
        from app.services.auth_policy import get_auth_policy

        policy = get_auth_policy(db_session)
        policy.access_token_minutes = 33
        db_session.commit()

        assert auth_routes._session_token_minutes(db_session) == 33
