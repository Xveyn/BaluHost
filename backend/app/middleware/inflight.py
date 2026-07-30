"""In-Flight-Zähler für die Concurrency-Probe (S1/#300).

Bewusst pure ASGI statt `BaseHTTPMiddleware`: der Stack hat davon bereits acht
(K9/#334), und ein Werkzeug, das Overhead messen soll, darf ihn nicht selbst
nennenswert erzeugen. Pure ASGI spart den Request/Response-Wrapper und die
zusätzliche Task-Gruppe, die BaseHTTPMiddleware pro Request aufzieht.
"""
from __future__ import annotations

import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.concurrency_probe import get_request_stats


class InFlightMiddleware:
    """Zählt laufende HTTP-Requests und ihre Bedienzeit.

    Die gemessene Dauer endet beim `http.response.start`, nicht am Ende des
    ASGI-Aufrufs. Sonst wäre sie die Lebensdauer der Verbindung: ein
    SSE-Stream (`/api/admin/backend-logs/stream`) oder ein 10-GB-Download
    lieferte eine Dauer von Minuten, und das p95 eines ruhigen Fensters wäre
    genau dieser eine Wert. In die Auslegung des Connection-Pools (PR2) darf
    Übertragungszeit nicht einfließen.

    Der In-Flight-Zähler umfasst dagegen weiterhin den GANZEN Aufruf — ein
    laufender Stream ist tatsächlich in flight, und `req_in_flight_*` soll das
    auch sagen.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        stats = get_request_stats()
        stats.record_start()
        started_at = time.perf_counter()
        response_started_at: float | None = None

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started_at
            # `.get()`, nicht `[...]`: dieser Wrapper liegt im Sende-Pfad JEDER
            # Response — ein KeyError hier wäre ein kaputter Request.
            if (
                response_started_at is None
                and message.get("type") == "http.response.start"
            ):
                response_started_at = time.perf_counter()
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            # Kam es nie zu einer Response (Exception vor dem ersten Byte),
            # wird die Gesamtdauer genommen — die Messung ganz zu verlieren
            # wäre schlechter.
            ended_at = (
                response_started_at
                if response_started_at is not None
                else time.perf_counter()
            )
            stats.record_end(ended_at - started_at)
