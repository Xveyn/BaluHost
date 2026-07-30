"""Concurrency-Instrumentierung für S1 (#300).

Misst pro Worker, wie stark der Event-Loop blockiert wird und wie viel
Nebenläufigkeit tatsächlich anfällt. Die Zahlen sind die Grundlage für die
Pool- und Threadpool-Grenzen in PR2 — ohne sie würden die Grenzen geraten.

Emittiert alle `concurrency_probe_interval_seconds` eine strukturierte
Logzeile auf dem Logger `baluhost.concurrency`.

Zwei Messarten, bewusst getrennt:
* **Gesampelt** (Loop-Lag, Threadpool, offene Verbindungen) — der Task tickt
  alle 250 ms und liest ab.
* **Gebucht** (Pool-Checkouts) — zwei SQLAlchemy-Listener auf Engine-Ebene
  zählen jeden Checkout in dem Thread, der ihn ausführt. Sampeln reichte hier
  nicht: Ein nicht-awaitender `async def` Handler hält die Verbindung, während
  der Loop blockiert ist — der Sampler kommt genau dann nicht dran.
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

from sqlalchemy import event
from sqlalchemy.engine import Engine

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
    duration_mean_ms: float | None
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
        # Summe/Anzahl laufen über ALLE Requests des Fensters, nicht nur über
        # die im gedeckelten Quantil-Puffer verbliebenen: Little's Law ist auf
        # der mittleren Bedienzeit definiert, und ein Mittelwert über die
        # letzten N Requests wäre eine andere Größe.
        self._duration_sum_ms = 0.0
        self._duration_count = 0

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
            duration_ms = duration_s * 1000.0
            self._durations.append(duration_ms)
            self._duration_sum_ms += duration_ms
            self._duration_count += 1

    def drain(self) -> RequestWindow:
        """Fenster abschließen: Aggregat zurückgeben und Zähler zurücksetzen.

        `in_flight` wird NICHT zurückgesetzt — es ist ein Live-Wert. Der
        High-Water-Mark startet beim aktuellen Stand, nicht bei null, sonst
        würde ein dauerhaft laufender Request unsichtbar.
        """
        with self._lock:
            durations = list(self._durations)
            mean_ms = (
                self._duration_sum_ms / self._duration_count
                if self._duration_count
                else None
            )
            window = RequestWindow(
                started=self._started,
                completed=self._completed,
                in_flight_now=self._in_flight,
                in_flight_max=self._in_flight_max,
                duration_mean_ms=mean_ms,
                duration_p50_ms=percentile(durations, 0.50),
                duration_p95_ms=percentile(durations, 0.95),
                duration_max_ms=max(durations) if durations else None,
            )
            self._started = 0
            self._completed = 0
            self._in_flight_max = self._in_flight
            self._durations.clear()
            self._duration_sum_ms = 0.0
            self._duration_count = 0
            return window


_request_stats = RequestStats()


def get_request_stats() -> RequestStats:
    """Prozessweites Singleton — die Middleware und der Probe-Task teilen es."""
    return _request_stats


@dataclass(frozen=True)
class PoolSample:
    """Momentaufnahme des SQLAlchemy-Connection-Pools.

    Nur noch für die statische Konfiguration (`size`, `max_overflow`) und für
    `open_connections` (belegt + leerlaufend) verwendet — die Belegung selbst
    kommt aus `PoolCheckoutTracker`, weil Point-Sampling sie systematisch
    verfehlt (siehe dort).
    """

    checked_out: int
    overflow: int
    open_connections: int
    size: int
    max_overflow: int | None


@dataclass(frozen=True)
class PoolWindow:
    """Exakte Checkout-Buchführung eines Fensters (Event-basiert)."""

    checkouts: int
    in_use_max: int
    #: None, wenn die Obergrenze des Pools unbekannt ist — dann wird über
    #: Sättigung nichts behauptet, statt "0" zu melden.
    saturation_events: int | None


def _pool_ceiling(engine: Engine) -> int | None:
    """`size + max_overflow`, oder None wenn der Pool keine Obergrenze kennt.

    Statische Konfiguration, einmal beim Anhängen gelesen — sie ändert sich
    über die Lebenszeit des Engines nicht, auch nicht über `engine.dispose()`
    hinweg (der neue Pool erbt dieselben Parameter).
    """
    pool = getattr(engine, "pool", None)
    size = getattr(pool, "size", None)
    max_overflow = getattr(pool, "_max_overflow", None)
    if not callable(size) or not isinstance(max_overflow, int):
        return None
    try:
        return int(size()) + max_overflow
    except Exception:
        logger.debug("Failed to read pool ceiling", exc_info=True)
        return None


class PoolCheckoutTracker:
    """Zählt Pool-Checkouts über SQLAlchemy-Events statt per Point-Sampling.

    Warum nicht sampeln: einen Checkout hält ein nicht-awaitender `async def`
    Handler von der ersten Query bis zum Teardown — und währenddessen ist der
    Event-Loop blockiert, der Probe-Task kommt also gar nicht dran. Genau die
    Belegung, um die es in #300 geht, wäre unsichtbar. Der Listener dagegen
    läuft synchron im Thread, der den Checkout ausführt, und sieht jeden
    einzelnen, unabhängig vom Zustand des Loops.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._in_use = 0
        self._in_use_max = 0
        self._checkouts = 0
        self._saturation_events = 0
        self._ceiling: int | None = None
        self._attached = False

    # ---- Registrierung -------------------------------------------------

    def attach(self, engine: Engine) -> bool:
        """Listener anhängen. Gibt False zurück, wenn schon angehängt.

        Idempotent: ein zweiter Aufruf (Probe zweimal gestartet, Tests) darf
        keinen zweiten Satz Listener registrieren, sonst zählte jeder Checkout
        doppelt. Auch ein FEHLGESCHLAGENER Versuch gilt als erledigt — sonst
        könnte ein halb registriertes Paar beim nächsten Anlauf zu einem
        doppelten Checkin-Listener werden.
        """
        with self._lock:
            if self._attached:
                return False
            self._attached = True

        self._ceiling = _pool_ceiling(engine)
        try:
            # checkin zuerst: schlägt das Registrieren dazwischen fehl, bleibt
            # höchstens ein Dekrement-Listener übrig (bei 0 abgefangen) statt
            # eines Inkrement-Listeners, der unbegrenzt hochliefe.
            event.listen(engine, "checkin", self._on_checkin)
            event.listen(engine, "checkout", self._on_checkout)
        except Exception:
            logger.warning(
                "Could not register pool checkout listeners; "
                "pool accounting stays empty",
                exc_info=True,
            )
            return False
        return True

    # ---- Listener ------------------------------------------------------
    #
    # Beide laufen INNERHALB von SQLAlchemys Checkout-/Checkin-Pfad. Eine
    # Exception hier bräche jede Datenbankoperation der Anwendung. Deshalb
    # fangen sie BaseException — bewusst breiter als `Exception`: eine
    # Diagnose darf unter keinen Umständen die Anwendung mitreißen, und diese
    # beiden Methoden tun nichts, wofür ein KeyboardInterrupt hier durchkommen
    # müsste.

    def _on_checkout(
        self, _dbapi_connection, _connection_record, _connection_proxy
    ) -> None:
        try:
            with self._lock:
                self._checkouts += 1
                self._in_use += 1
                if self._in_use > self._in_use_max:
                    self._in_use_max = self._in_use
                # Sättigung ist jetzt exakt bestimmbar statt gesampelt: dieser
                # Checkout hat die letzte freie Verbindung genommen — nur aus
                # diesem Zustand heraus kann der nächste in pool_timeout laufen.
                if self._ceiling is not None and self._in_use >= self._ceiling:
                    self._saturation_events += 1
        except BaseException:
            _swallow_listener_error()

    def _on_checkin(self, _dbapi_connection, _connection_record) -> None:
        try:
            with self._lock:
                if self._in_use > 0:
                    self._in_use -= 1
        except BaseException:
            _swallow_listener_error()

    # ---- Auslesen ------------------------------------------------------

    def drain(self) -> PoolWindow:
        """Fenster abschließen. `in_use_max` startet beim aktuellen Stand,
        damit eine dauerhaft gehaltene Verbindung nicht unsichtbar wird."""
        with self._lock:
            window = PoolWindow(
                checkouts=self._checkouts,
                in_use_max=self._in_use_max,
                saturation_events=(
                    self._saturation_events if self._ceiling is not None else None
                ),
            )
            self._checkouts = 0
            self._saturation_events = 0
            self._in_use_max = self._in_use
            return window


def _swallow_listener_error() -> None:
    """Fehler im Tracker dürfen nie in den Checkout-Pfad zurückschlagen —
    auch das Loggen selbst nicht."""
    try:
        logger.debug("Pool checkout listener failed", exc_info=True)
    except BaseException:
        pass


_pool_tracker = PoolCheckoutTracker()


def get_pool_tracker() -> PoolCheckoutTracker:
    """Prozessweites Singleton — ein Satz Listener pro Worker."""
    return _pool_tracker


@dataclass(frozen=True)
class ThreadPoolSample:
    """Momentaufnahme des anyio-Threadpools, in dem sync Endpoints laufen."""

    borrowed: int
    waiting: int
    total_tokens: float


def sample_pool(engine: Engine) -> PoolSample | None:
    """Pool-Zustand punktuell ablesen (statische Konfiguration + offene
    Verbindungen).

    Gibt None zurück, wenn der Pool keine Zähler führt — NullPool und der in
    den Tests verwendete StaticPool haben checkedout()/overflow() nicht.

    `_max_overflow` ist privat, aber die einzige Quelle für die Obergrenze;
    SQLAlchemy exponiert sie nicht öffentlich. Fehlt sie (andere Pool-Klasse,
    andere SQLAlchemy-Version), wird `max_overflow=None` gemeldet, statt eine
    Obergrenze zu erfinden.

    Achtung: `open_connections` besteht aus zwei nicht-atomaren Lesevorgängen
    (`checkedout()` + `checkedin()`). Eine Verbindung, die genau dazwischen
    zurückgegeben wird, zählt in beiden — der Wert hat dadurch einen kleinen
    systematischen Aufwärts-Bias.
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
    pool_window: PoolWindow | None = None,
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
        "req_duration_mean_ms": _rounded(request_window.duration_mean_ms),
        "req_duration_p50_ms": _rounded(request_window.duration_p50_ms),
        "req_duration_p95_ms": _rounded(request_window.duration_p95_ms),
        "req_duration_max_ms": _rounded(request_window.duration_max_ms),
        # Aus der Checkout-Buchführung: vollständig, unabhängig davon, ob der
        # Event-Loop während des Checkouts blockiert war.
        "pool_checkouts": pool_window.checkouts if pool_window else None,
        "pool_in_use_max": pool_window.in_use_max if pool_window else None,
        # Vorläufer eines Pool-Timeouts: Checkouts, die die letzte freie
        # Verbindung genommen haben.
        "pool_saturation_events": (
            pool_window.saturation_events if pool_window else None
        ),
        # Punktuell gesampelt (belegt + leerlaufend): die Event-Buchführung
        # kennt leerlaufende Verbindungen nicht.
        "pool_open_max": pool.open_connections if pool else None,
        "pool_size": pool.size if pool else None,
        "pool_max_overflow": pool.max_overflow if pool else None,
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
    tracker = get_pool_tracker()
    tracker.attach(engine)
    # Alles, was vor dem ersten Fenster gezählt wurde (Startup-Queries),
    # gehört in kein Fenster.
    tracker.drain()

    lags_ms: list[float] = []
    pool_high: PoolSample | None = None
    threadpool_high: ThreadPoolSample | None = None
    window_started = time.perf_counter()

    while True:
        tick_started = time.perf_counter()
        await asyncio.sleep(tick_seconds)
        elapsed = time.perf_counter() - tick_started
        lags_ms.append(max(0.0, (elapsed - tick_seconds) * 1000.0))

        pool_high = _merge_pool_high_water(pool_high, sample_pool(engine))
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
            pool_window=tracker.drain(),
        )
        logger.info(
            "concurrency window: loop_lag_p95=%sms in_flight_max=%s pool_in_use_max=%s",
            payload["loop_lag_p95_ms"],
            payload["req_in_flight_max"],
            payload["pool_in_use_max"],
            extra=payload,
        )

        lags_ms = []
        pool_high = None
        threadpool_high = None
        window_started = time.perf_counter()
