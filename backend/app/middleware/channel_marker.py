"""Marks each incoming request with its trust channel (local|remote).

The channel value comes from a provider callable (in production wired to
settings.channel via main.py). Using a callable instead of a fixed __init__
value lets tests monkeypatch settings without rebuilding the app.

An attacker on the TCP-bound process cannot spoof local-channel status
regardless of headers — the channel value is taken from server-side config,
not the request.
"""
import logging
from typing import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

VALID_CHANNELS = {"local", "remote"}


class ChannelMarkerMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        channel_provider: Callable[[], str],
        loopback_fallback_provider: Callable[[], bool] = lambda: False,
        is_dev_provider: Callable[[], bool] = lambda: False,
    ):
        super().__init__(app)
        self._channel_provider = channel_provider
        self._loopback_fallback_provider = loopback_fallback_provider
        self._is_dev_provider = is_dev_provider

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        channel = self._channel_provider()
        if channel not in VALID_CHANNELS:
            raise ValueError(
                f"Invalid channel '{channel}' — must be one of {VALID_CHANNELS}"
            )

        # Dev-only loopback fallback
        if (
            channel == "remote"
            and self._loopback_fallback_provider()
            and self._is_dev_provider()
        ):
            host = request.client.host if request.client else None
            if host in {"127.0.0.1", "::1"} or (host or "").startswith("::ffff:127."):
                channel = "local"

        request.state.channel = channel
        return await call_next(request)
