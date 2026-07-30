"""Concurrency-Instrumentierung für S1 (#300).

Misst pro Worker, wie stark der Event-Loop blockiert wird und wie viel
Nebenläufigkeit tatsächlich anfällt. Die Zahlen sind die Grundlage für die
Pool- und Threadpool-Grenzen in PR2 — ohne sie würden die Grenzen geraten.

Emittiert alle `concurrency_probe_interval_seconds` eine strukturierte
Logzeile auf dem Logger `baluhost.concurrency`.
"""
from __future__ import annotations

import anyio.to_thread
import asyncio
import logging
import math
import os
import threading
import time
from collections import deque
from dataclasses import dataclass

logger = logging.getLogger("baluhost.concurrency")

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
        logger.debug("Failed to sample pool; continuing without sample", exc_info=True)
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
        logger.debug(
            "Failed to sample threadpool; continuing without sample", exc_info=True
        )
        return None

    return ThreadPoolSample(
        borrowed=stats.borrowed_tokens,
        waiting=stats.tasks_waiting,
        total_tokens=stats.total_tokens,
    )


def build_window_payload(
    *,
    window_seconds: float,
    lags_ms: list[float],
    request_window: RequestWindow,
    pool: PoolSample | None,
    threadpool: ThreadPoolSample | None,
    pool_saturated_ticks: int = 0,
) -> dict[str, object]:
    """Ein Messfenster in flache, log-taugliche Felder überführen.

    Alle Keys sind bewusst so benannt, dass sie nicht mit LogRecord-Attributen
    kollidieren (deshalb `worker_pid` statt `process`) — sonst wirft logging
    beim `extra=`-Merge einen KeyError.
    """
    return {
        "window_seconds": round(window_seconds, 3),
        "ticks": len(lags_ms),
        "loop_lag_p50_ms": _rounded(percentile(lags_ms, 0.50)),
        "loop_lag_p95_ms": _rounded(percentile(lags_ms, 0.95)),
        "loop_lag_max_ms": _rounded(max(lags_ms) if lags_ms else None),
        "req_started": request_window.started,
        "req_completed": request_window.completed,
        "req_in_flight_now": request_window.in_flight_now,
        "req_in_flight_max": request_window.in_flight_max,
        "req_duration_p50_ms": _rounded(request_window.duration_p50_ms),
        "req_duration_p95_ms": _rounded(request_window.duration_p95_ms),
        "req_duration_max_ms": _rounded(request_window.duration_max_ms),
        "pool_checked_out_max": pool.checked_out if pool else None,
        "pool_overflow_max": pool.overflow if pool else None,
        "pool_open_max": pool.open_connections if pool else None,
        "pool_size": pool.size if pool else None,
        "pool_max_overflow": pool.max_overflow if pool else None,
        # Vorläufer eines Pool-Timeouts: nur aus einem voll ausgeschöpften
        # Pool heraus kann ein Checkout in den pool_timeout laufen.
        "pool_saturated_ticks": pool_saturated_ticks,
        "threadpool_borrowed_max": threadpool.borrowed if threadpool else None,
        "threadpool_waiting_max": threadpool.waiting if threadpool else None,
        "threadpool_total_tokens": threadpool.total_tokens if threadpool else None,
        "worker_pid": os.getpid(),
    }


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


def _merge_pool_high_water(
    current: PoolSample | None, sample: PoolSample | None
) -> PoolSample | None:
    """High-Water-Marks über die Ticks eines Fensters führen."""
    if sample is None:
        return current
    if current is None:
        return sample
    return PoolSample(
        checked_out=max(current.checked_out, sample.checked_out),
        overflow=max(current.overflow, sample.overflow),
        open_connections=max(current.open_connections, sample.open_connections),
        size=sample.size,
        max_overflow=sample.max_overflow,
    )


def _merge_threadpool_high_water(
    current: ThreadPoolSample | None, sample: ThreadPoolSample | None
) -> ThreadPoolSample | None:
    if sample is None:
        return current
    if current is None:
        return sample
    return ThreadPoolSample(
        borrowed=max(current.borrowed, sample.borrowed),
        waiting=max(current.waiting, sample.waiting),
        total_tokens=sample.total_tokens,
    )


async def concurrency_probe_loop(
    interval_seconds: float | None = None,
    tick_seconds: float = 0.25,
) -> None:
    """Ein Task pro Worker: tickt, misst, meldet.

    Der Event-Loop-Lag ist die Leitkennzahl von #300: gemessen wird, um wie
    viel ein `sleep(tick_seconds)` seine Sollzeit überschreitet. Blockiert
    eine synchrone DB-Query den Loop, schlägt sich das genau hier nieder.
    """
    from app.core.config import settings
    from app.core.database import engine

    if interval_seconds is None:
        interval_seconds = float(settings.concurrency_probe_interval_seconds)

    stats = get_request_stats()
    lags_ms: list[float] = []
    pool_high: PoolSample | None = None
    threadpool_high: ThreadPoolSample | None = None
    saturated_ticks = 0
    window_started = time.perf_counter()

    while True:
        tick_started = time.perf_counter()
        await asyncio.sleep(tick_seconds)
        elapsed = time.perf_counter() - tick_started
        lags_ms.append(max(0.0, (elapsed - tick_seconds) * 1000.0))

        pool_sample = sample_pool(engine)
        if pool_sample is not None and pool_sample.is_saturated:
            saturated_ticks += 1
        pool_high = _merge_pool_high_water(pool_high, pool_sample)
        threadpool_high = _merge_threadpool_high_water(
            threadpool_high, sample_threadpool()
        )

        window_elapsed = time.perf_counter() - window_started
        if window_elapsed < interval_seconds:
            continue

        payload = build_window_payload(
            window_seconds=window_elapsed,
            lags_ms=lags_ms,
            request_window=stats.drain(),
            pool=pool_high,
            threadpool=threadpool_high,
            pool_saturated_ticks=saturated_ticks,
        )
        logger.info(
            "concurrency window: loop_lag_p95=%sms in_flight_max=%s pool_out_max=%s",
            payload["loop_lag_p95_ms"],
            payload["req_in_flight_max"],
            payload["pool_checked_out_max"],
            extra=payload,
        )

        lags_ms = []
        pool_high = None
        threadpool_high = None
        saturated_ticks = 0
        window_started = time.perf_counter()
