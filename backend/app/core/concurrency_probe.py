"""Concurrency-Instrumentierung für S1 (#300).

Misst pro Worker, wie stark der Event-Loop blockiert wird und wie viel
Nebenläufigkeit tatsächlich anfällt. Die Zahlen sind die Grundlage für die
Pool- und Threadpool-Grenzen in PR2 — ohne sie würden die Grenzen geraten.

Emittiert alle `concurrency_probe_interval_seconds` eine strukturierte
Logzeile auf dem Logger `baluhost.concurrency`.
"""
from __future__ import annotations

import math
import threading
from collections import deque
from dataclasses import dataclass

# Wie viele Request-Dauern pro Fenster für die Quantile vorgehalten werden.
# Die Zähler (`started`/`completed`) sind davon unberührt — nur die Quantile
# beziehen sich auf die letzten N Requests des Fensters.
_DEFAULT_MAX_SAMPLES = 5000


def percentile(values: list[float], q: float) -> float | None:
    """Nächster-Rang-Perzentil. Gibt None zurück, wenn keine Werte vorliegen."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(q * len(ordered)))
    return ordered[rank - 1]


@dataclass(frozen=True)
class RequestWindow:
    """Aggregat eines Messfensters."""

    started: int
    completed: int
    in_flight_now: int
    in_flight_max: int
    duration_p50_ms: float | None
    duration_p95_ms: float | None
    duration_max_ms: float | None


class RequestStats:
    """Thread-sichere Request-Zähler mit High-Water-Marks pro Fenster."""

    def __init__(self, max_samples: int = _DEFAULT_MAX_SAMPLES) -> None:
        self._lock = threading.Lock()
        self._in_flight = 0
        self._in_flight_max = 0
        self._started = 0
        self._completed = 0
        self._durations: deque[float] = deque(maxlen=max_samples)

    def record_start(self) -> None:
        with self._lock:
            self._started += 1
            self._in_flight += 1
            if self._in_flight > self._in_flight_max:
                self._in_flight_max = self._in_flight

    def record_end(self, duration_s: float) -> None:
        with self._lock:
            self._completed += 1
            if self._in_flight > 0:
                self._in_flight -= 1
            self._durations.append(duration_s * 1000.0)

    def drain(self) -> RequestWindow:
        """Fenster abschließen: Aggregat zurückgeben und Zähler zurücksetzen.

        `in_flight` wird NICHT zurückgesetzt — es ist ein Live-Wert. Der
        High-Water-Mark startet beim aktuellen Stand, nicht bei null, sonst
        würde ein dauerhaft laufender Request unsichtbar.
        """
        with self._lock:
            durations = list(self._durations)
            window = RequestWindow(
                started=self._started,
                completed=self._completed,
                in_flight_now=self._in_flight,
                in_flight_max=self._in_flight_max,
                duration_p50_ms=percentile(durations, 0.50),
                duration_p95_ms=percentile(durations, 0.95),
                duration_max_ms=max(durations) if durations else None,
            )
            self._started = 0
            self._completed = 0
            self._in_flight_max = self._in_flight
            self._durations.clear()
            return window


_request_stats = RequestStats()


def get_request_stats() -> RequestStats:
    """Prozessweites Singleton — die Middleware und der Probe-Task teilen es."""
    return _request_stats
