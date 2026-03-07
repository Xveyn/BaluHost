"""
API Version Middleware.

Adds X-API-Version and X-API-Min-Version headers to all /api/ responses.
Clients can use these headers to detect server API version at any time.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from app.core.config import settings


class ApiVersionMiddleware(BaseHTTPMiddleware):
    """Adds API version headers to all API responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        if request.url.path.startswith(settings.api_prefix):
            response.headers["X-API-Version"] = settings.api_version
            response.headers["X-API-Min-Version"] = settings.api_min_version
        return response
