"""
Error Counter Middleware for FastAPI.

Counts 4xx and 5xx HTTP responses with minimal overhead.
Used for admin debugging dashboard to monitor API error rates.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import threading


class ErrorCounterMiddleware(BaseHTTPMiddleware):
    """
    Middleware that counts HTTP error responses.

    Thread-safe counters for:
    - 4xx client errors
    - 5xx server errors

    Access counts via class attributes:
        ErrorCounterMiddleware.error_count_4xx
        ErrorCounterMiddleware.error_count_5xx
    """

    # Thread-safe counters (class-level for global access)
    _lock = threading.Lock()
    _error_count_4xx: int = 0
    _error_count_5xx: int = 0

    @classmethod
    @property
    def error_count_4xx(cls) -> int:
        """Get current 4xx error count."""
        with cls._lock:
            return cls._error_count_4xx

    @classmethod
    @property
    def error_count_5xx(cls) -> int:
        """Get current 5xx error count."""
        with cls._lock:
            return cls._error_count_5xx

    @classmethod
    def get_counts(cls) -> tuple[int, int]:
        """Get both error counts atomically. Returns (4xx_count, 5xx_count)."""
        with cls._lock:
            return cls._error_count_4xx, cls._error_count_5xx

    @classmethod
    def reset_counts(cls) -> None:
        """Reset error counts to zero (for testing)."""
        with cls._lock:
            cls._error_count_4xx = 0
            cls._error_count_5xx = 0

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        status_code = response.status_code

        if 400 <= status_code < 500:
            with self._lock:
                ErrorCounterMiddleware._error_count_4xx += 1
        elif status_code >= 500:
            with self._lock:
                ErrorCounterMiddleware._error_count_5xx += 1

        return response


def get_error_counts() -> tuple[int, int]:
    """
    Get current error counts.

    Returns:
        Tuple of (4xx_count, 5xx_count)
    """
    return ErrorCounterMiddleware.get_counts()
