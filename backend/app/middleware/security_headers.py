"""
Security Headers Middleware for FastAPI.

Adds security headers to all HTTP responses:
- Content-Security-Policy (CSP)
- X-Content-Type-Options
- X-Frame-Options  
- Strict-Transport-Security (HSTS)
- Referrer-Policy
"""

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from app.core.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        
        # Content Security Policy - Prevents inline scripts and external script injection
        # policy: default-src 'self' - only allow resources from same origin
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "  # Vite dev server needs eval
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self' https:; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        
        # Prevents MIME-sniffing attacks
        # Tells browser to respect the Content-Type header
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # Prevents clickjacking attacks
        # Disallows framing the app in iframes
        response.headers["X-Frame-Options"] = "DENY"
        
        # Prevents browsers from leaking referrer information
        response.headers["Referrer-Policy"] = "strict-no-referrer"
        
        # Permissions Policy (formerly Feature-Policy)
        # Restricts browser features
        response.headers["Permissions-Policy"] = (
            "geolocation=(), "
            "microphone=(), "
            "camera=(), "
            "payment=()"
        )
        
        # HTTPS enforcement in production
        if not settings.debug:
            # Strict-Transport-Security
            # Forces HTTPS for 1 year (31536000 seconds)
            # includeSubDomains applies policy to all subdomains
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )
        
        return response


def setup_security_headers(app: FastAPI) -> None:
    """
    Setup security headers middleware on FastAPI app.
    
    Should be called early in app initialization:
    
    ```python
    app = FastAPI()
    setup_security_headers(app)
    # ... other middleware and routes
    ```
    """
    app.add_middleware(SecurityHeadersMiddleware)
