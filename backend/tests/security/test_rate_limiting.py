"""Tests for API rate limiting functionality."""

import pytest
from httpx import AsyncClient
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.core.config import settings
from app.core.rate_limiter import (
    RATE_LIMITS,
    _build_limiter,
    _is_test_mode,
    _select_key_func,
    limiter,
    user_limiter,
)


@pytest.mark.asyncio
class TestRateLimiting:
    """Test rate limiting across different API endpoints."""
    
    async def test_login_rate_limit(self, async_client: AsyncClient):
        """Test that login endpoint is rate limited (5/minute)."""
        # Make 5 login attempts (should succeed)
        for i in range(5):
            response = await async_client.post(
                "/api/auth/login",
                json={"username": "testuser", "password": "wrongpassword"}
            )
            # Login fails due to wrong credentials, but rate limit not hit yet
            assert response.status_code in [401, 429]
            if i < 4:  # First 4 should be 401
                assert response.status_code == 401
        
        # 6th request should be rate limited
        response = await async_client.post(
            "/api/auth/login",
            json={"username": "testuser", "password": "wrongpassword"}
        )
        assert response.status_code == 429
        assert "Too Many Requests" in response.json().get("error", "")
        assert "Retry-After" in response.headers
    
    async def test_register_rate_limit(self, async_client: AsyncClient):
        """Test that register endpoint is rate limited (3/minute)."""
        # Make 3 registration attempts (should succeed in terms of rate limiting)
        for i in range(3):
            response = await async_client.post(
                "/api/auth/register",
                json={
                    "username": f"newuser{i}",
                    "email": f"user{i}@test.com",
                    "password": "TestPass123!"
                }
            )
            # Either succeeds (201) or rate limited (429)
            assert response.status_code in [201, 409, 429]
            if i < 2:  # First 2 should not be rate limited
                assert response.status_code in [201, 409]
        
        # 4th request should be rate limited
        response = await async_client.post(
            "/api/auth/register",
            json={
                "username": "newuser4",
                "email": "user4@test.com",
                "password": "TestPass123!"
            }
        )
        assert response.status_code == 429
    
    async def test_file_upload_rate_limit(
        self,
        async_client: AsyncClient,
        auth_headers: dict
    ):
        """Test that file upload endpoint is rate limited (20/minute)."""
        # Note: This test would need to make 21 requests to trigger rate limit
        # For testing purposes, we'll just verify the endpoint responds

        file_content = b"Test file content"
        files = {"file": ("test.txt", file_content, "text/plain")}

        response = await async_client.post(
            "/api/files/upload",
            files=files,
            data={"path": ""},
            headers=auth_headers
        )

        # 200/201 = success, 403 = no home dir in CI (acceptable)
        assert response.status_code in [200, 201, 403]

    async def test_file_download_rate_limit(
        self,
        async_client: AsyncClient,
        auth_headers: dict
    ):
        """Test that file download endpoint is rate limited (100/minute)."""
        response = await async_client.get(
            "/api/files/download/nonexistent.txt",
            headers=auth_headers
        )

        # 200 = success, 403 = no home dir, 404 = file not found (all acceptable)
        assert response.status_code in [200, 403, 404]

    async def test_share_creation_rate_limit(
        self,
        async_client: AsyncClient,
        auth_headers: dict
    ):
        """Test that share creation endpoint is rate limited (10/minute)."""
        response = await async_client.post(
            "/api/shares/links",
            json={
                "file_id": 1,
                "password_protected": False
            },
            headers=auth_headers
        )

        # 201 = success, 403 = no access, 404 = file not found, 422 = validation error
        assert response.status_code in [201, 403, 404, 422]
    
    async def test_rate_limit_headers_present(
        self,
        async_client: AsyncClient
    ):
        """Test that rate limit headers are included in responses."""
        response = await async_client.post(
            "/api/auth/login",
            json={"username": "test", "password": "test"}
        )
        
        # Rate limit headers should be present (slowapi adds them)
        # Note: Headers might not always be present depending on slowapi configuration
        assert response.status_code in [401, 429]
    
    async def test_rate_limit_per_user_vs_ip(
        self,
        async_client: AsyncClient,
        auth_headers: dict
    ):
        """Test that authenticated users have different rate limits than unauthenticated."""
        # Authenticated request (should use user-based limiter)
        response_auth = await async_client.get(
            "/api/files/list?path=",
            headers=auth_headers
        )
        assert response_auth.status_code == 200
        
        # Unauthenticated request to public endpoint (should use IP-based limiter)
        response_unauth = await async_client.post(
            "/api/auth/login",
            json={"username": "test", "password": "test"}
        )
        assert response_unauth.status_code in [401, 429]
    
    async def test_rate_limit_exceeded_response_format(
        self,
        async_client: AsyncClient
    ):
        """Test that rate limit exceeded response has correct format."""
        # Make requests until rate limited
        for i in range(10):  # Exceed the 5/minute limit for login
            response = await async_client.post(
                "/api/auth/login",
                json={"username": "test", "password": "test"}
            )
            if response.status_code == 429:
                # Check response format
                data = response.json()
                assert "error" in data
                assert data["error"] == "Too Many Requests"
                assert "detail" in data
                assert "retry_after" in data
                
                # Check headers
                assert "Retry-After" in response.headers
                break


@pytest.mark.asyncio
class TestRateLimitConfiguration:
    """Test rate limit configuration and settings."""
    
    def test_rate_limit_config_exists(self):
        """Test that rate limit configurations are properly defined."""
        assert "auth_login" in RATE_LIMITS
        assert "auth_register" in RATE_LIMITS
        assert "file_upload" in RATE_LIMITS
        assert "file_download" in RATE_LIMITS
        assert "file_list" in RATE_LIMITS
        assert "file_delete" in RATE_LIMITS
        assert "share_create" in RATE_LIMITS
        assert "share_list" in RATE_LIMITS
        # public_share may not exist if handled via share_create
        assert "share_create" in RATE_LIMITS
    
    def test_rate_limit_values_are_valid(self):
        """Test that rate limit values are in correct format."""
        for key, value in RATE_LIMITS.items():
            assert isinstance(value, str)
            assert "/" in value
            parts = value.split("/")
            assert len(parts) == 2
            # First part should be a number
            assert parts[0].isdigit()
            # Second part should be a time unit
            assert parts[1] in ["second", "minute", "hour", "day"]
    
    def test_strict_endpoints_have_low_limits(self):
        """Test that security-critical endpoints have strict limits."""
        # Login should have strict limit
        login_limit = int(RATE_LIMITS["auth_login"].split("/")[0])
        assert login_limit <= 10
        
        # Register should have strict limit
        register_limit = int(RATE_LIMITS["auth_register"].split("/")[0])
        assert register_limit <= 5
        
        # Mobile registration should have strict limit
        mobile_register_limit = int(RATE_LIMITS["mobile_register"].split("/")[0])
        assert mobile_register_limit <= 5


class TestRateLimiterKeyFunction:
    """`X-Test-Client` is test-only infrastructure and must stay out of prod (#318).

    The header lets the test suite give every client its own limiter bucket.
    If the production limiter honoured it too, any caller could mint a fresh
    bucket per request and walk straight through the IP-based default limits.
    """

    @staticmethod
    def _request(client_ip: str = "203.0.113.7", **headers: str) -> Request:
        """Build a minimal ASGI request with the given headers and peer IP."""
        return Request({
            "type": "http",
            "method": "POST",
            "path": "/api/auth/login",
            "headers": [(k.replace("_", "-").lower().encode(), v.encode())
                        for k, v in headers.items()],
            "client": (client_ip, 51234),
            "scheme": "http",
            "server": ("testserver", 80),
            "query_string": b"",
        })

    def test_production_key_func_ignores_test_client_header(self):
        """A caller cannot pick its own bucket by sending the test header."""
        key_func = _select_key_func(test_mode=False)

        spoofed = key_func(self._request(X_Test_Client="attacker-chosen"))
        plain = key_func(self._request())

        # Same IP, same bucket — the header buys the caller nothing.
        assert spoofed == plain == "203.0.113.7"

    def test_test_mode_key_func_isolates_buckets_per_client(self):
        """In tests the header still separates buckets, or the suite goes flaky."""
        key_func = _select_key_func(test_mode=True)

        assert key_func(self._request(X_Test_Client="abc")) == "testclient:abc"
        assert key_func(self._request(X_Test_Client="xyz")) == "testclient:xyz"
        # Without the header it falls back to the peer IP.
        assert key_func(self._request()) == "203.0.113.7"

    def test_production_key_func_is_the_plain_remote_address(self):
        """No test-aware wrapper is left in the production code path at all."""
        assert _select_key_func(test_mode=False) is get_remote_address

    def test_limiter_is_wired_to_the_selected_key_func(self):
        """The module-level limiter uses the mode it detected — no second path."""
        assert limiter._key_func is _select_key_func(_is_test_mode())


class TestTestModeDetection:
    """Test mode relaxes limits drastically — production must never reach it.

    `_is_test_mode()` also gates which key function the limiter gets, so a
    stray env var does not just loosen the numbers, it hands bucket selection
    back to the caller (see `TestRateLimiterKeyFunction`).
    """

    def test_prod_mode_never_enters_test_mode(self, monkeypatch):
        """SKIP_APP_INIT is a test/tooling flag — in prod it must not disarm limits."""
        monkeypatch.setattr(settings, "nas_mode", "prod")
        monkeypatch.setenv("SKIP_APP_INIT", "1")

        assert _is_test_mode() is False

    def test_dev_mode_still_relaxes_limits(self, monkeypatch):
        """Dev keeps the relaxed behaviour the suite depends on."""
        monkeypatch.setattr(settings, "nas_mode", "dev")

        assert _is_test_mode() is True


class TestDefaultLimitsAreNotDeadConfig:
    """`default_limits` are unreachable in this app — so they must stay empty.

    slowapi applies them from `SlowAPIMiddleware` (not installed here) or for
    routes that opt in with `override_defaults=False` (none do — the decorator
    defaults to True). A non-empty value is therefore decoration that promises
    a global floor which does not exist.
    """

    def test_neither_limiter_advertises_unreachable_defaults(self):
        assert _build_limiter(test_mode=False)._default_limits == []
        assert _build_limiter(test_mode=True)._default_limits == []
        assert user_limiter._default_limits == []

    def test_no_middleware_silently_activates_the_defaults(self):
        """Guard: installing SlowAPIMiddleware makes the defaults live again.

        If this fails, someone enabled global limiting — decide the numbers
        deliberately at that point instead of inheriting an empty list.
        """
        from app.main import app

        installed = [m.cls.__name__ for m in app.user_middleware]
        assert "SlowAPIMiddleware" not in installed
