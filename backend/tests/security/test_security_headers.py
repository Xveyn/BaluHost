"""
Security Headers & HTTPS Configuration Tests for Task 2.3.

Tests cover:
1. Security headers are sent with all responses
2. HTTPS is enforced in production
3. HSTS header configuration
4. CSP (Content Security Policy) setup
5. CORS properly configured
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a TestClient from the main app."""
    from app.main import app

    return TestClient(app)


class TestSecurityHeaders:
    """Test that security headers are properly configured."""

    def test_content_security_policy_header_present(self, client):
        """Verify CSP header is set on all responses."""
        response = client.get("/api/health")

        headers = {k.lower(): v for k, v in response.headers.items()}
        assert "content-security-policy" in headers
        csp = headers["content-security-policy"]
        assert "default-src 'self'" in csp
        assert "script-src" in csp

    def test_x_content_type_options_header_set(self, client):
        """Verify X-Content-Type-Options: nosniff header."""
        response = client.get("/api/health")

        headers = {k.lower(): v for k, v in response.headers.items()}
        assert headers.get("x-content-type-options") == "nosniff"

    def test_x_frame_options_header_prevents_clickjacking(self, client):
        """Verify X-Frame-Options header prevents iframe embedding."""
        response = client.get("/api/health")

        headers = {k.lower(): v for k, v in response.headers.items()}
        assert headers.get("x-frame-options") in ("DENY", "SAMEORIGIN")

    @pytest.mark.skip(reason="HSTS only sent over HTTPS; requires TLS test infrastructure")
    def test_strict_transport_security_header_in_production(self, client):
        """Verify HSTS header forces HTTPS in production."""
        pass

    def test_referrer_policy_header_set(self, client):
        """Verify Referrer-Policy header controls referrer information."""
        response = client.get("/api/health")

        headers = {k.lower(): v for k, v in response.headers.items()}
        assert headers.get("referrer-policy") == "strict-no-referrer"

    def test_permissions_policy_header_set(self, client):
        """Verify Permissions-Policy restricts browser features."""
        response = client.get("/api/health")

        headers = {k.lower(): v for k, v in response.headers.items()}
        assert "permissions-policy" in headers
        pp = headers["permissions-policy"]
        assert "geolocation=()" in pp
        assert "camera=()" in pp


class TestHTTPSConfiguration:
    """Test HTTPS configuration requirements."""

    @pytest.mark.skip(reason="Requires HTTPS infrastructure; BaluHost uses WireGuard VPN for external access")
    def test_https_enabled_in_production(self):
        """Verify HTTPS is enforced in production environment."""
        pass

    @pytest.mark.skip(reason="Requires nginx/reverse proxy infrastructure test")
    def test_http_redirect_to_https_in_production(self):
        """Verify HTTP requests redirect to HTTPS in production."""
        pass

    @pytest.mark.skip(reason="Requires TLS certificate infrastructure test")
    def test_certificate_validation(self):
        """Verify TLS certificate is properly configured."""
        pass

    @pytest.mark.skip(reason="Requires TLS infrastructure test")
    def test_tls_version_minimum_1_2(self):
        """Verify minimum TLS version is 1.2."""
        pass

    @pytest.mark.skip(reason="Requires TLS infrastructure test")
    def test_strong_cipher_suites_configured(self):
        """Verify strong cipher suites are enabled."""
        pass


class TestCORSConfiguration:
    """Test CORS (Cross-Origin Resource Sharing) security."""

    def test_cors_origins_whitelist_enforced(self, client):
        """Verify CORS only allows whitelisted origins."""
        allowed_origin = "http://localhost:5173"
        response = client.options(
            "/api/health",
            headers={"Origin": allowed_origin, "Access-Control-Request-Method": "GET"},
        )

        headers = {k.lower(): v for k, v in response.headers.items()}
        assert headers.get("access-control-allow-origin") == allowed_origin

    def test_cors_rejects_unknown_origins(self, client):
        """Verify CORS rejects unauthorized origins."""
        disallowed_origin = "https://malicious-site.com"
        response = client.get(
            "/api/health",
            headers={"Origin": disallowed_origin},
        )

        headers = {k.lower(): v for k, v in response.headers.items()}
        # Disallowed origin should not be reflected in Allow-Origin
        assert headers.get("access-control-allow-origin") != disallowed_origin

    def test_cors_credentials_only_with_specific_origins(self, client):
        """Verify CORS credentials are restricted to specific origins."""
        allowed_origin = "http://localhost:5173"
        response = client.options(
            "/api/health",
            headers={"Origin": allowed_origin, "Access-Control-Request-Method": "GET"},
        )

        headers = {k.lower(): v for k, v in response.headers.items()}
        if headers.get("access-control-allow-credentials") == "true":
            # When credentials are allowed, origin must be specific (not *)
            assert headers.get("access-control-allow-origin") != "*"


class TestSecureSessionConfiguration:
    """Test secure session and cookie settings."""

    @pytest.mark.skip(reason="BaluHost uses JWT Bearer auth, not session cookies")
    def test_session_cookie_secure_flag_set(self):
        """Verify Secure flag prevents HTTP cookie transmission."""
        pass

    @pytest.mark.skip(reason="BaluHost uses JWT Bearer auth, not session cookies")
    def test_session_cookie_httponly_flag_set(self):
        """Verify HttpOnly flag prevents JavaScript access."""
        pass

    @pytest.mark.skip(reason="BaluHost uses JWT Bearer auth, not session cookies")
    def test_session_cookie_samesite_attribute_set(self):
        """Verify SameSite attribute prevents CSRF."""
        pass


class TestSecurityHeadersMiddleware:
    """Test security headers middleware implementation."""

    def test_all_endpoints_have_security_headers(self, client):
        """Verify multiple endpoints include security headers."""
        endpoints = ["/api/health", "/docs", "/redoc"]

        for endpoint in endpoints:
            response = client.get(endpoint)
            headers = {k.lower(): v for k, v in response.headers.items()}

            assert "x-content-type-options" in headers, f"{endpoint} missing X-Content-Type-Options"
            assert "x-frame-options" in headers, f"{endpoint} missing X-Frame-Options"
            assert "referrer-policy" in headers, f"{endpoint} missing Referrer-Policy"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
