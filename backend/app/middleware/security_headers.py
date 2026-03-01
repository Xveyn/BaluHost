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
        # In dev mode, allow 'unsafe-inline' and 'unsafe-eval' for Vite HMR.
        # In production, only 'self' is permitted for script-src to prevent XSS.
        # style-src keeps 'unsafe-inline' in both modes because Tailwind CSS injects
        # styles at runtime (removing it would break the UI in production builds).
        if settings.is_dev_mode:
            script_src = "'self' 'unsafe-inline' 'unsafe-eval'"
        else:
            script_src = "'self'"
        style_src = "'self' 'unsafe-inline'"

        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            f"script-src {script_src}; "
            f"style-src {style_src}; "
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
        
        # HSTS — only send when the request actually arrived over HTTPS.
        # Sending HSTS over plain HTTP locks browsers out for max-age.
        if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
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
