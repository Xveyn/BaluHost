"""Tests for POST /api/plugins/{name}/_audit/scope-denied.

Verifies that:
- An authenticated user can POST a scope-denial report and receive 2xx.
- The request body is validated (Pydantic schema — raw dict not accepted).
- Unauthenticated requests are rejected.
- The audit logger's log_event is called with the expected arguments.

Auth pattern: uses the ``client`` and ``user_headers`` / ``admin_headers``
fixtures from conftest.py (in-memory DB, real JWT auth flow).

Assertions are UNCONDITIONAL — status code is always asserted before any
further checks.
"""
from unittest.mock import MagicMock, patch

import pytest


ROUTE = "/api/plugins/my-plugin/_audit/scope-denied"
VALID_BODY = {"method": "get", "url": "/api/users"}


# ---------------------------------------------------------------------------
# Positive path — any authenticated user can post
# ---------------------------------------------------------------------------

def test_scope_denied_audit_as_user_returns_200(client, user_headers):
    """A regular authenticated user posting a scope-denied report gets 200."""
    resp = client.post(ROUTE, json=VALID_BODY, headers=user_headers)
    assert resp.status_code == 200, (
        f"Expected 200 from POST {ROUTE}; got {resp.status_code}. Body: {resp.text[:500]}"
    )
    data = resp.json()
    assert data.get("recorded") is True, (
        f"Expected {{\"recorded\": true}} in response; got {data!r}"
    )


def test_scope_denied_audit_as_admin_returns_200(client, admin_headers):
    """An admin user posting a scope-denied report also gets 200."""
    resp = client.post(ROUTE, json=VALID_BODY, headers=admin_headers)
    assert resp.status_code == 200, (
        f"Expected 200 from POST {ROUTE} as admin; got {resp.status_code}. Body: {resp.text[:500]}"
    )
    assert resp.json().get("recorded") is True


# ---------------------------------------------------------------------------
# Audit logger is called with the right arguments
# ---------------------------------------------------------------------------

def test_scope_denied_audit_calls_log_event(client, user_headers):
    """log_event must be called with event_type=PLUGIN, action=scope_denied, success=False."""
    mock_logger = MagicMock()

    # get_audit_logger_db is imported at module level in plugins.py, so we
    # patch the name as seen by the route module.
    with patch(
        "app.api.routes.plugins.get_audit_logger_db",
        return_value=mock_logger,
    ):
        resp = client.post(
            "/api/plugins/weather/_audit/scope-denied",
            json={"method": "post", "url": "/api/admin/users"},
            headers=user_headers,
        )

    assert resp.status_code == 200, (
        f"Expected 200; got {resp.status_code}. Body: {resp.text[:500]}"
    )

    mock_logger.log_event.assert_called_once()
    call_kwargs = mock_logger.log_event.call_args

    # Support both positional and keyword argument styles
    kwargs = call_kwargs.kwargs if call_kwargs.kwargs else {}
    args = call_kwargs.args if call_kwargs.args else ()

    # Convert positional args to named for assertions (matches function signature)
    # log_event(event_type, user, action, resource, success, details, ip_address)
    # Route uses keyword args only, so check kwargs
    assert kwargs.get("event_type") == "PLUGIN", f"event_type wrong: {kwargs}"
    assert kwargs.get("action") == "scope_denied", f"action wrong: {kwargs}"
    assert kwargs.get("success") is False, f"success should be False: {kwargs}"
    assert kwargs.get("resource") == "weather", f"resource (plugin name) wrong: {kwargs}"
    details = kwargs.get("details", {})
    assert details.get("method") == "post", f"details.method wrong: {details}"
    assert details.get("url") == "/api/admin/users", f"details.url wrong: {details}"


# ---------------------------------------------------------------------------
# Authentication enforcement
# ---------------------------------------------------------------------------

def test_scope_denied_audit_unauthenticated_returns_401(client):
    """Unauthenticated requests must be rejected (401 or 403)."""
    resp = client.post(ROUTE, json=VALID_BODY)
    assert resp.status_code in (401, 403), (
        f"Expected 401/403 for unauthenticated request; got {resp.status_code}. Body: {resp.text[:200]}"
    )


# ---------------------------------------------------------------------------
# Body validation — missing required fields
# ---------------------------------------------------------------------------

def test_scope_denied_audit_missing_body_returns_422(client, user_headers):
    """Missing required fields must return 422 (Pydantic validation)."""
    resp = client.post(ROUTE, json={}, headers=user_headers)
    assert resp.status_code == 422, (
        f"Expected 422 for empty body; got {resp.status_code}. Body: {resp.text[:300]}"
    )


def test_scope_denied_audit_missing_url_returns_422(client, user_headers):
    """Body with only 'method' (missing 'url') must return 422."""
    resp = client.post(ROUTE, json={"method": "get"}, headers=user_headers)
    assert resp.status_code == 422, (
        f"Expected 422 for body missing 'url'; got {resp.status_code}. Body: {resp.text[:300]}"
    )
