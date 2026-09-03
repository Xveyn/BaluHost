"""Admin-configurable session limits: idle logout + access-token TTL.

Both numbers were hardcoded before - 4 min + 60 s in the frontend hook, 15 min
in ``config.py``. The pair is coupled: an idle window longer than the token's
life means the session dies without the warning dialog ever showing, which is
exactly the state the production box was in.
"""
from __future__ import annotations

import pytest

from app.core.config import settings

ADMIN_URL = f"{settings.api_prefix}/admin/auth-policy"
SESSION_URL = f"{settings.api_prefix}/auth/session-policy"


class TestPolicyFields:
    def test_defaults_match_the_previously_hardcoded_values(self, client, admin_headers):
        """The migration must not change behavior on the day it lands."""
        body = client.get(ADMIN_URL, headers=admin_headers).json()

        assert body["idle_timeout_minutes"] == 4
        assert body["idle_warning_seconds"] == 60
        assert body["access_token_minutes"] == 15

    def test_round_trip(self, client, admin_headers):
        r = client.put(
            ADMIN_URL,
            headers=admin_headers,
            json={
                "idle_timeout_minutes": 30,
                "idle_warning_seconds": 120,
                "access_token_minutes": 720,
            },
        )

        assert r.status_code == 200, r.text
        assert r.json()["idle_timeout_minutes"] == 30
        assert r.json()["access_token_minutes"] == 720
        # and it survives a re-read, not just the echo
        assert client.get(ADMIN_URL, headers=admin_headers).json()["idle_warning_seconds"] == 120

    def test_zero_disables_the_idle_logout(self, client, admin_headers):
        r = client.put(ADMIN_URL, headers=admin_headers, json={"idle_timeout_minutes": 0})

        assert r.status_code == 200, r.text
        assert r.json()["idle_timeout_minutes"] == 0

    @pytest.mark.parametrize(
        "payload",
        [
            {"idle_timeout_minutes": -1},
            {"idle_timeout_minutes": 1441},
            {"idle_warning_seconds": 9},
            {"idle_warning_seconds": 301},
            {"access_token_minutes": 4},
            {"access_token_minutes": 1441},
        ],
    )
    def test_out_of_range_is_rejected(self, client, admin_headers, payload):
        assert client.put(ADMIN_URL, headers=admin_headers, json=payload).status_code == 422


class TestIdleWindowMustFitInTheToken:
    """The trap this feature exists to close.

    With idle 30 min against a 15 min token, the user is thrown out at minute
    15 by a 401 - no dialog, no countdown. Refuse the combination instead of
    letting an admin configure a lie.
    """

    def test_idle_window_longer_than_the_token_is_refused(self, client, admin_headers):
        r = client.put(
            ADMIN_URL,
            headers=admin_headers,
            json={"idle_timeout_minutes": 30, "access_token_minutes": 15},
        )

        assert r.status_code == 400, r.text
        assert "token" in r.json()["detail"].lower()

    def test_the_warning_seconds_count_towards_the_window(self, client, admin_headers):
        """15 min idle + 60 s warning is 16 minutes, one minute too long."""
        r = client.put(
            ADMIN_URL,
            headers=admin_headers,
            json={
                "idle_timeout_minutes": 15,
                "idle_warning_seconds": 60,
                "access_token_minutes": 15,
            },
        )

        assert r.status_code == 400, r.text

    def test_an_exactly_fitting_window_is_accepted(self, client, admin_headers):
        r = client.put(
            ADMIN_URL,
            headers=admin_headers,
            json={
                "idle_timeout_minutes": 14,
                "idle_warning_seconds": 60,
                "access_token_minutes": 15,
            },
        )

        assert r.status_code == 200, r.text

    def test_a_partial_update_is_checked_against_the_stored_values(
        self, client, admin_headers
    ):
        """PUT is a patch. Lowering only the token must still be validated
        against the idle window already in the database, or the check is
        trivially bypassed by sending one field at a time."""
        client.put(
            ADMIN_URL,
            headers=admin_headers,
            json={"idle_timeout_minutes": 60, "access_token_minutes": 120},
        )

        r = client.put(ADMIN_URL, headers=admin_headers, json={"access_token_minutes": 15})

        assert r.status_code == 400, r.text

    def test_a_disabled_idle_logout_lifts_the_constraint(self, client, admin_headers):
        """With no idle logout the token IS the only limit - that is honest,
        not a misconfiguration."""
        r = client.put(
            ADMIN_URL,
            headers=admin_headers,
            json={"idle_timeout_minutes": 0, "access_token_minutes": 5},
        )

        assert r.status_code == 200, r.text


class TestSessionPolicyReadRoute:
    """The idle hook runs for every user, so the read path cannot be admin-only."""

    def test_a_plain_user_may_read_the_idle_values(self, client, user_headers):
        r = client.get(SESSION_URL, headers=user_headers)

        assert r.status_code == 200, r.text
        assert r.json() == {"idle_timeout_minutes": 4, "idle_warning_seconds": 60}

    def test_it_does_not_leak_the_token_ttl_or_the_pin_policy(self, client, admin_headers):
        """Only what the hook needs. The token TTL is nothing the client acts on."""
        body = client.get(SESSION_URL, headers=admin_headers).json()

        assert set(body) == {"idle_timeout_minutes", "idle_warning_seconds"}

    def test_it_reflects_an_admin_change(self, client, admin_headers, user_headers):
        client.put(ADMIN_URL, headers=admin_headers, json={"idle_timeout_minutes": 10})

        assert client.get(SESSION_URL, headers=user_headers).json()["idle_timeout_minutes"] == 10

    def test_anonymous_callers_are_rejected(self, client):
        assert client.get(SESSION_URL).status_code in (401, 403)
