"""In-Flight-Zähler für die Concurrency-Probe (S1/#300).

Bewusst pure ASGI statt `BaseHTTPMiddleware`: der Stack hat davon bereits acht
(K9/#334), und ein Werkzeug, das Overhead messen soll, darf ihn nicht selbst
nennenswert erzeugen. Pure ASGI spart den Request/Response-Wrapper und die
zusätzliche Task-Gruppe, die BaseHTTPMiddleware pro Request aufzieht.
"""
from __future__ import annotations

import time

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.concurrency_probe import get_request_stats


class InFlightMiddleware:
    """Zählt laufende HTTP-Requests und ihre Gesamtdauer."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        stats = get_request_stats()
        stats.record_start()
        started_at = time.perf_counter()
        try:
            await self.app(scope, receive, send)
        finally:
            stats.record_end(time.perf_counter() - started_at)
