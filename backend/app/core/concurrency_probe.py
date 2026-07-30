"""Concurrency-Instrumentierung für S1 (#300).

Misst pro Worker, wie stark der Event-Loop blockiert wird und wie viel
Nebenläufigkeit tatsächlich anfällt. Die Zahlen sind die Grundlage für die
Pool- und Threadpool-Grenzen in PR2 — ohne sie würden die Grenzen geraten.

Emittiert alle `concurrency_probe_interval_seconds` eine strukturierte
Logzeile auf dem Logger `baluhost.concurrency`.
"""
from __future__ import annotations

import anyio.to_thread
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


@dataclass(frozen=True)
class PoolSample:
    """Momentaufnahme des SQLAlchemy-Connection-Pools."""

    checked_out: int
    overflow: int
    open_connections: int
    size: int
    max_overflow: int | None

    @property
    def is_saturated(self) -> bool:
        """True, wenn keine weitere Verbindung mehr vergeben werden kann.

        Nur aus diesem Zustand heraus kann ein Checkout in den `pool_timeout`
        laufen. Ist die Obergrenze unbekannt, wird nichts behauptet.
        """
        if self.max_overflow is None:
            return False
        return self.checked_out >= self.size + self.max_overflow


@dataclass(frozen=True)
class ThreadPoolSample:
    """Momentaufnahme des anyio-Threadpools, in dem sync Endpoints laufen."""

    borrowed: int
    waiting: int
    total_tokens: float


def sample_pool(engine) -> PoolSample | None:
    """Pool-Auslastung ablesen.

    Gibt None zurück, wenn der Pool keine Zähler führt — NullPool und der in
    den Tests verwendete StaticPool haben checkedout()/overflow() nicht.

    `_max_overflow` ist privat, aber die einzige Quelle für die Obergrenze;
    SQLAlchemy exponiert sie nicht öffentlich. Fehlt sie (andere Pool-Klasse,
    andere SQLAlchemy-Version), degradiert `is_saturated` still zu False,
    statt eine falsche Sättigung zu melden.
    """
    pool = getattr(engine, "pool", None)
    if pool is None:
        return None

    checked_out = getattr(pool, "checkedout", None)
    overflow = getattr(pool, "overflow", None)
    checked_in = getattr(pool, "checkedin", None)
    size = getattr(pool, "size", None)
    if not all(callable(fn) for fn in (checked_out, overflow, checked_in, size)):
        return None

    try:
        out = checked_out()
        # QueuePool.overflow() startet bei -pool_size und wächst. Roh geloggt
        # wäre "-5" nicht interpretierbar; gemeldet wird die Zahl der
        # Verbindungen jenseits von pool_size.
        raw_overflow = overflow()
        max_overflow = getattr(pool, "_max_overflow", None)
        return PoolSample(
            checked_out=out,
            overflow=max(0, raw_overflow),
            open_connections=out + checked_in(),
            size=size(),
            max_overflow=max_overflow if isinstance(max_overflow, int) else None,
        )
    except Exception:
        return None


def sample_threadpool() -> ThreadPoolSample | None:
    """anyio-Threadpool ablesen — dort laufen sync Endpoints.

    Gibt None zurück, wenn kein Event-Loop läuft: der Limiter hängt an einer
    RunVar und ist außerhalb des Loops nicht erreichbar.
    """
    try:
        limiter = anyio.to_thread.current_default_thread_limiter()
        stats = limiter.statistics()
    except Exception:
        return None

    return ThreadPoolSample(
        borrowed=stats.borrowed_tokens,
        waiting=stats.tasks_waiting,
        total_tokens=stats.total_tokens,
    )
