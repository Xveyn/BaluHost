# S1 / PR1 — Concurrency-Instrumentierung: Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Messen, wie stark synchrone DB-Arbeit den Event-Loop blockiert und wie viel Nebenläufigkeit tatsächlich anfällt — als Grundlage für die Grenzwerte in PR2.

**Architecture:** Eine pure-ASGI-Middleware zählt laufende Requests und ihre Dauer. Ein einzelner Lifespan-Task tickt alle 250 ms, misst daraus den Event-Loop-Lag und liest DB-Pool und anyio-Threadpool ab. Alle 60 s wird ein Fenster mit High-Water-Marks als eine strukturierte Logzeile ausgegeben und zurückgesetzt. Kein Verhaltenswechsel an bestehenden Routen.

**Tech Stack:** Python 3.11+, FastAPI 0.115.6, Starlette 0.41.3, SQLAlchemy 2.0.44, anyio 4.11, pytest (`asyncio_mode = "auto"`), `python-json-logger`.

**Spec:** `docs/superpowers/specs/2026-07-30-s1-sync-sqlalchemy-event-loop-design.md`
**Issue:** [#300](https://github.com/Xveyn/BaluHost/issues/300)
**Branch:** `feat/s1-concurrency-probe` (existiert bereits, enthält den Spec-Commit)

## Global Constraints

- **Keine neuen Abhängigkeiten.** Alles mit stdlib + bereits installierten Paketen.
- **Rein additiv.** Kein bestehender Route-Handler wird in diesem PR angefasst. Das `async def` → `def`-Flippen ist PR2.
- **Pure ASGI, kein `BaseHTTPMiddleware`.** Der Stack hat bereits 8 davon (K9/#334); der Overhead-Messer darf ihn nicht vergrößern.
- **Background-Task nur über `_spawn_background()`** aus `app/core/lifespan.py:64`. Nie ein nacktes `asyncio.create_task` (K2/#320).
- **Tests laufen aus `backend/`**: `cd backend; python -m pytest ...`
- **Ruff muss grün sein**: `cd backend; python -m ruff check app tests`
- **Windows-Repo mit `core.autocrlf=true`.** Dateien mit LF schreiben, Git konvertiert.
- **Kein `shell=True`, keine Secrets ins Log.** Die Probe protokolliert ausschließlich Zahlen.
- **Logger-Name ist `baluhost.concurrency`** — genau dieser String, damit `journalctl` danach filtern kann.
- **`extra=`-Keys dürfen nicht mit `LogRecord`-Attributen kollidieren.** Verboten sind unter anderem `message`, `name`, `module`, `process`, `args`, `levelname`, `asctime`. Deshalb heißt das PID-Feld `worker_pid`, nicht `process`.

---

## File Structure

| Datei | Verantwortung |
|---|---|
| `backend/app/core/concurrency_probe.py` *(neu)* | Zustand und Messung: `RequestStats`, Perzentil-Helfer, Pool-/Threadpool-Ableser, `concurrency_probe_loop()` |
| `backend/app/middleware/inflight.py` *(neu)* | Pure-ASGI-Middleware, die `RequestStats` füttert |
| `backend/app/main.py` *(ändern)* | Middleware als äußerste registrieren |
| `backend/app/core/config.py` *(ändern)* | `concurrency_probe_enabled`, `concurrency_probe_interval_seconds` |
| `backend/app/core/lifespan.py` *(ändern)* | Task starten (jeder Worker, nicht nur primary) |
| `backend/app/api/routes/metrics.py` *(ändern)* | `baluhost_database_connections` befüllen |
| `backend/tests/core/test_concurrency_probe.py` *(neu)* | Task 1, 3, 4 |
| `backend/tests/middleware/test_inflight.py` *(neu)* | Task 2 |
| `backend/tests/core/test_concurrency_probe_wiring.py` *(neu)* | Task 5 |
| `backend/tests/api/test_metrics_db_connections.py` *(neu)* | Task 6 |
| `backend/app/middleware/CLAUDE.md`, `backend/app/core/CLAUDE.md`, `docs/monitoring/CONCURRENCY_PROBE.md` *(neu/ändern)* | Task 7 |

Warum `concurrency_probe.py` alles außer der Middleware trägt: Zustand, Sampler und Reporter ändern sich gemeinsam und werden gemeinsam gelesen. Die Middleware ist der einzige Teil, der eine fremde Schnittstelle (ASGI) bedient — deshalb liegt nur sie separat.

---

### Task 1: Request-Statistik und Perzentile

**Files:**
- Create: `backend/app/core/concurrency_probe.py`
- Test: `backend/tests/core/test_concurrency_probe.py`

**Interfaces:**
- Consumes: nichts
- Produces:
  - `percentile(values: list[float], q: float) -> float | None`
  - `class RequestStats` mit `record_start() -> None`, `record_end(duration_s: float) -> None`, `drain() -> RequestWindow`
  - `@dataclass RequestWindow` mit den Feldern `started: int`, `completed: int`, `in_flight_now: int`, `in_flight_max: int`, `duration_p50_ms: float | None`, `duration_p95_ms: float | None`, `duration_max_ms: float | None`
  - `get_request_stats() -> RequestStats` (Prozess-Singleton)

- [ ] **Step 1: Write the failing test**

Erzeuge `backend/tests/core/test_concurrency_probe.py`:

```python
"""Tests für die Concurrency-Probe (S1/#300, PR1)."""
import pytest

from app.core.concurrency_probe import (
    RequestStats,
    get_request_stats,
    percentile,
)


class TestPercentile:
    def test_returns_none_for_empty_input(self):
        assert percentile([], 0.5) is None

    def test_single_value_is_every_percentile(self):
        assert percentile([7.0], 0.5) == 7.0
        assert percentile([7.0], 0.95) == 7.0

    def test_p50_of_ten_values(self):
        values = [float(v) for v in range(1, 11)]  # 1..10
        assert percentile(values, 0.5) == 5.0

    def test_p95_picks_the_high_tail(self):
        values = [float(v) for v in range(1, 101)]  # 1..100
        assert percentile(values, 0.95) == 95.0

    def test_input_order_does_not_matter(self):
        assert percentile([9.0, 1.0, 5.0], 0.5) == 5.0


class TestRequestStats:
    def test_fresh_stats_drain_to_zero(self):
        stats = RequestStats()
        window = stats.drain()
        assert window.started == 0
        assert window.completed == 0
        assert window.in_flight_now == 0
        assert window.in_flight_max == 0
        assert window.duration_p50_ms is None

    def test_counts_started_and_completed(self):
        stats = RequestStats()
        stats.record_start()
        stats.record_end(0.010)
        window = stats.drain()
        assert window.started == 1
        assert window.completed == 1
        assert window.in_flight_now == 0

    def test_in_flight_max_is_the_high_water_mark(self):
        stats = RequestStats()
        stats.record_start()
        stats.record_start()
        stats.record_start()
        stats.record_end(0.001)
        window = stats.drain()
        assert window.in_flight_max == 3
        assert window.in_flight_now == 2

    def test_durations_are_reported_in_milliseconds(self):
        stats = RequestStats()
        for seconds in (0.001, 0.002, 0.003):
            stats.record_start()
            stats.record_end(seconds)
        window = stats.drain()
        assert window.duration_max_ms == pytest.approx(3.0)
        assert window.duration_p50_ms == pytest.approx(2.0)

    def test_drain_resets_counters_but_keeps_live_in_flight(self):
        stats = RequestStats()
        stats.record_start()
        stats.record_start()
        stats.record_end(0.001)
        stats.drain()

        window = stats.drain()
        assert window.started == 0
        assert window.completed == 0
        assert window.in_flight_now == 1, "ein Request läuft noch"
        assert window.in_flight_max == 1, "High-Water startet beim aktuellen Stand"

    def test_duration_buffer_is_bounded(self):
        stats = RequestStats(max_samples=10)
        for _ in range(50):
            stats.record_start()
            stats.record_end(0.001)
        window = stats.drain()
        assert window.completed == 50, "Zähler zählt alle"
        assert window.duration_max_ms is not None, "Quantile aus den letzten 10"

    def test_get_request_stats_is_a_singleton(self):
        assert get_request_stats() is get_request_stats()
```

- [ ] **Step 2: Run test to verify it fails**

```
cd backend
python -m pytest tests/core/test_concurrency_probe.py -v --no-cov
```

Erwartet: `ModuleNotFoundError: No module named 'app.core.concurrency_probe'`

- [ ] **Step 3: Write minimal implementation**

Erzeuge `backend/app/core/concurrency_probe.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

```
cd backend
python -m pytest tests/core/test_concurrency_probe.py -v --no-cov
```

Erwartet: alle Tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/concurrency_probe.py backend/tests/core/test_concurrency_probe.py
git commit -m "feat(probe): request statistics with per-window high-water marks (#300)"
```

---

### Task 2: In-Flight-Middleware (pure ASGI)

**Files:**
- Create: `backend/app/middleware/inflight.py`
- Modify: `backend/app/main.py` (nach der `CORSMiddleware`-Registrierung, aktuell Zeile 148-154)
- Test: `backend/tests/middleware/test_inflight.py`

**Interfaces:**
- Consumes: `get_request_stats()` aus Task 1
- Produces: `class InFlightMiddleware` mit `__init__(self, app: ASGIApp)` und `async __call__(self, scope, receive, send)`

- [ ] **Step 1: Write the failing test**

Erzeuge `backend/tests/middleware/test_inflight.py`:

```python
"""Tests für die In-Flight-Middleware (S1/#300, PR1)."""
import asyncio

import httpx
import pytest
from fastapi import FastAPI

from app.core.concurrency_probe import RequestStats
from app.middleware.inflight import InFlightMiddleware


@pytest.fixture
def stats(monkeypatch) -> RequestStats:
    """Frische Statistik, damit Tests sich nicht über das Singleton beeinflussen."""
    fresh = RequestStats()
    monkeypatch.setattr(
        "app.middleware.inflight.get_request_stats", lambda: fresh
    )
    return fresh


@pytest.fixture
def app() -> FastAPI:
    application = FastAPI()

    @application.get("/ok")
    async def ok():
        return {"ok": True}

    @application.get("/slow")
    async def slow():
        await asyncio.sleep(0.05)
        return {"ok": True}

    @application.get("/boom")
    async def boom():
        raise RuntimeError("kaputt")

    application.add_middleware(InFlightMiddleware)
    return application


async def _get(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        return await client.get(path)


async def test_counts_a_single_request(stats, app):
    await _get(app, "/ok")

    window = stats.drain()
    assert window.started == 1
    assert window.completed == 1
    assert window.in_flight_now == 0
    assert window.duration_max_ms is not None


async def test_in_flight_max_reflects_real_concurrency(stats, app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        await asyncio.gather(*(client.get("/slow") for _ in range(3)))

    window = stats.drain()
    assert window.started == 3
    assert window.in_flight_max == 3
    assert window.in_flight_now == 0


async def test_counter_is_released_when_the_handler_raises(stats, app):
    with pytest.raises(RuntimeError):
        await _get(app, "/boom")

    window = stats.drain()
    assert window.started == 1
    assert window.completed == 1
    assert window.in_flight_now == 0, "kein Leck bei Exceptions"


async def test_non_http_scopes_are_passed_through_untouched(stats):
    seen = []

    async def inner_app(scope, receive, send):
        seen.append(scope["type"])

    middleware = InFlightMiddleware(inner_app)
    await middleware({"type": "lifespan"}, None, None)

    assert seen == ["lifespan"]
    window = stats.drain()
    assert window.started == 0, "Lifespan ist kein Request"
```

- [ ] **Step 2: Run test to verify it fails**

```
cd backend
python -m pytest tests/middleware/test_inflight.py -v --no-cov
```

Erwartet: `ModuleNotFoundError: No module named 'app.middleware.inflight'`

- [ ] **Step 3: Write minimal implementation**

Erzeuge `backend/app/middleware/inflight.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

```
cd backend
python -m pytest tests/middleware/test_inflight.py -v --no-cov
```

Erwartet: alle Tests PASS.

- [ ] **Step 5: Register the middleware as the outermost layer**

In `backend/app/main.py`: den Import bei den übrigen Middleware-Imports ergänzen und die Registrierung **nach** dem `app.add_middleware(CORSMiddleware, ...)`-Block (aktuell Zeile 148-154) einfügen.

`add_middleware()` macht `user_middleware.insert(0, ...)` — die **zuletzt** registrierte Middleware ist die äußerste. Sie muss außen liegen, damit die gemessene Dauer den kompletten Stack enthält und nicht nur den Teil innerhalb von CORS.

```python
from app.middleware.inflight import InFlightMiddleware
```

```python
    # Concurrency-Probe (S1/#300): zählt laufende Requests und ihre Dauer.
    # Bewusst als letzte registriert = äußerste Schicht, damit die gemessene
    # Dauer den gesamten Middleware-Stack einschließt.
    app.add_middleware(InFlightMiddleware)
```

- [ ] **Step 6: Verify the app still starts and the existing suite is unaffected**

```
cd backend
python -m pytest tests/middleware -v --no-cov
python -m pytest tests/api -q --no-cov
```

Erwartet: PASS, keine neuen Fehler.

- [ ] **Step 7: Commit**

```bash
git add backend/app/middleware/inflight.py backend/tests/middleware/test_inflight.py backend/app/main.py
git commit -m "feat(probe): pure-ASGI in-flight middleware as the outermost layer (#300)"
```

---

### Task 3: Pool- und Threadpool-Ableser

**Files:**
- Modify: `backend/app/core/concurrency_probe.py`
- Test: `backend/tests/core/test_concurrency_probe.py` (ergänzen)

**Interfaces:**
- Consumes: nichts aus Task 1/2
- Produces:
  - `sample_pool(engine) -> PoolSample | None`
  - `@dataclass PoolSample` mit `checked_out: int`, `overflow: int`, `open_connections: int`, `size: int`, `max_overflow: int | None`
  - `PoolSample.is_saturated: bool` (Property)
  - `sample_threadpool() -> ThreadPoolSample | None`
  - `@dataclass ThreadPoolSample` mit `borrowed: int`, `waiting: int`, `total_tokens: float`

**Abweichung vom Spec, bewusst:** Der Spec nennt einen „Zähler für Pool-Timeouts".
Ein echter Timeout-Zähler bräuchte einen Hook an jedem Connection-Checkout —
den gibt es nicht, ohne `get_db` und jeden `SessionLocal()`-Aufruf anzufassen,
und genau das soll PR1 nicht tun. Stattdessen wird der **Vorläufer** gezählt:
Ticks, in denen der Pool voll ausgeschöpft war (`pool_saturated_ticks`). Ein
Timeout kann nur aus diesem Zustand entstehen; ein Fenster mit
`pool_saturated_ticks == 0` beweist, dass kein Timeout möglich war.

> **Korrektur nach dem Abschluss-Review (2026-07-30, Befund C1) — der Absatz
> oben ist überholt.** Beide Aussagen waren falsch:
> 1. Ein Checkout-Hook braucht `get_db` *nicht*. `event.listen(engine,
>    "checkout"/"checkin", …)` hängt auf **Engine-Ebene** und lässt jeden
>    Aufrufer unangetastet — dieselbe Bauform, die `core/database.py:92`/`:113`
>    schon verwendet. Umgesetzt als `PoolCheckoutTracker`.
> 2. `pool_saturated_ticks == 0` bewies gar nichts. Point-Sampling vom
>    Event-Loop aus ist genau dann blind, wenn ein nicht-awaitender `async def`
>    Handler eine Verbindung hält — denn dann kommt der Sampler-Task nicht
>    dran. Sättigung kürzer als ein Tick war ohnehin unsichtbar.
>
> Ersetzt durch die exakte Buchführung `pool_checkouts` / `pool_in_use_max` /
> `pool_saturation_events`. Die Beweis-Behauptung ist aus beiden Guides
> entfernt. Der Test `test_sees_what_point_sampling_structurally_cannot`
> hält den Unterschied fest.

- [ ] **Step 1: Write the failing test**

An `backend/tests/core/test_concurrency_probe.py` anhängen:

```python
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool, StaticPool

from app.core.concurrency_probe import (
    PoolSample,
    ThreadPoolSample,
    sample_pool,
    sample_threadpool,
)


class TestSamplePool:
    def test_reads_a_queuepool(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path / 'probe.db'}")
        sample = sample_pool(engine)

        assert isinstance(sample, PoolSample)
        assert sample.size == 5
        assert sample.checked_out == 0
        assert sample.open_connections == 0

    def test_counts_a_checked_out_connection(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path / 'probe.db'}")
        with engine.connect():
            sample = sample_pool(engine)

        assert sample is not None
        assert sample.checked_out == 1
        assert sample.open_connections == 1

    def test_overflow_is_normalised_to_zero_or_more(self, tmp_path):
        """QueuePool.overflow() startet bei -pool_size. Roh wäre das im Log
        irreführend — gemeldet wird, wie viele Verbindungen über pool_size
        hinaus existieren."""
        engine = create_engine(f"sqlite:///{tmp_path / 'probe.db'}")
        sample = sample_pool(engine)

        assert sample is not None
        assert sample.overflow == 0

    def test_reports_the_overflow_ceiling(self, tmp_path):
        """Ohne max_overflow lässt sich Sättigung nicht erkennen."""
        engine = create_engine(
            f"sqlite:///{tmp_path / 'probe.db'}", pool_size=3, max_overflow=7
        )
        sample = sample_pool(engine)

        assert sample is not None
        assert sample.size == 3
        assert sample.max_overflow == 7

    def test_is_saturated_only_when_the_ceiling_is_reached(self):
        headroom = PoolSample(
            checked_out=5, overflow=0, open_connections=5, size=3, max_overflow=7
        )
        full = PoolSample(
            checked_out=10, overflow=7, open_connections=10, size=3, max_overflow=7
        )
        unknown = PoolSample(
            checked_out=99, overflow=0, open_connections=99, size=3, max_overflow=None
        )

        assert headroom.is_saturated is False
        assert full.is_saturated is True
        assert unknown.is_saturated is False, "ohne Obergrenze keine Behauptung"

    def test_returns_none_for_a_pool_without_counters(self, tmp_path):
        engine = create_engine(
            f"sqlite:///{tmp_path / 'probe.db'}", poolclass=NullPool
        )
        assert sample_pool(engine) is None

    def test_returns_none_for_staticpool_used_in_tests(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        assert sample_pool(engine) is None


class TestSampleThreadPool:
    async def test_reads_the_anyio_limiter(self):
        sample = sample_threadpool()

        assert isinstance(sample, ThreadPoolSample)
        assert sample.total_tokens > 0
        assert sample.borrowed >= 0
        assert sample.waiting >= 0

    def test_returns_none_outside_an_event_loop(self):
        assert sample_threadpool() is None
```

- [ ] **Step 2: Run test to verify it fails**

```
cd backend
python -m pytest tests/core/test_concurrency_probe.py -v --no-cov
```

Erwartet: `ImportError: cannot import name 'PoolSample'`

- [ ] **Step 3: Write minimal implementation**

An `backend/app/core/concurrency_probe.py` anhängen (Imports oben ergänzen):

```python
import anyio.to_thread
```

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

```
cd backend
python -m pytest tests/core/test_concurrency_probe.py -v --no-cov
```

Erwartet: alle Tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/concurrency_probe.py backend/tests/core/test_concurrency_probe.py
git commit -m "feat(probe): pool and threadpool samplers with graceful degradation (#300)"
```

---

### Task 4: Loop-Lag-Messung und Fenster-Reporter

**Files:**
- Modify: `backend/app/core/concurrency_probe.py`
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/core/test_concurrency_probe.py` (ergänzen)

**Interfaces:**
- Consumes: `RequestStats`, `percentile`, `sample_pool`, `sample_threadpool` aus Tasks 1 und 3
- Produces:
  - `build_window_payload(...) -> dict[str, object]`
  - `async concurrency_probe_loop(interval_seconds: float | None = None, tick_seconds: float = 0.25) -> None`
  - Settings `concurrency_probe_enabled: bool`, `concurrency_probe_interval_seconds: int`

- [ ] **Step 1: Add the settings**

In `backend/app/core/config.py` in der `Settings`-Klasse ergänzen (bei den übrigen einfachen Feldern):

```python
    # Concurrency-Probe (S1/#300): misst Event-Loop-Lag, In-Flight-Requests,
    # DB-Pool- und Threadpool-Auslastung. Grundlage für die Grenzwerte in PR2.
    concurrency_probe_enabled: bool = True
    concurrency_probe_interval_seconds: int = 60
```

Env-Variablen sind `CONCURRENCY_PROBE_ENABLED` und `CONCURRENCY_PROBE_INTERVAL_SECONDS` (Feldname in Großbuchstaben, wie bei `enforce_local_only` → `ENFORCE_LOCAL_ONLY`).

- [ ] **Step 2: Write the failing test**

An `backend/tests/core/test_concurrency_probe.py` anhängen:

```python
import asyncio
import logging

from app.core.concurrency_probe import (
    build_window_payload,
    concurrency_probe_loop,
)

# LogRecord-Attribute, die von `extra=` NICHT überschrieben werden dürfen —
# logging wirft dann KeyError. Der Test hält die Payload-Keys davon frei.
_RESERVED_LOGRECORD_KEYS = {
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "message", "module",
    "msecs", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "thread", "threadName", "taskName",
}


class TestBuildWindowPayload:
    def test_payload_keys_never_collide_with_logrecord_attributes(self):
        stats = RequestStats()
        stats.record_start()
        stats.record_end(0.01)

        payload = build_window_payload(
            window_seconds=60.0,
            lags_ms=[1.0, 2.0, 3.0],
            request_window=stats.drain(),
            pool=PoolSample(
                checked_out=2,
                overflow=0,
                open_connections=3,
                size=5,
                max_overflow=10,
            ),
            threadpool=ThreadPoolSample(borrowed=1, waiting=0, total_tokens=40),
        )

        collisions = set(payload) & _RESERVED_LOGRECORD_KEYS
        assert collisions == set(), f"würde logging sprengen: {collisions}"

    def test_saturated_ticks_are_carried_through(self):
        payload = build_window_payload(
            window_seconds=60.0,
            lags_ms=[],
            request_window=RequestStats().drain(),
            pool=None,
            threadpool=None,
            pool_saturated_ticks=17,
        )

        assert payload["pool_saturated_ticks"] == 17

    def test_payload_carries_the_loop_lag_quantiles(self):
        payload = build_window_payload(
            window_seconds=60.0,
            lags_ms=[float(v) for v in range(1, 101)],
            request_window=RequestStats().drain(),
            pool=None,
            threadpool=None,
        )

        assert payload["loop_lag_p50_ms"] == 50.0
        assert payload["loop_lag_p95_ms"] == 95.0
        assert payload["loop_lag_max_ms"] == 100.0

    def test_missing_samplers_degrade_to_none_not_crash(self):
        payload = build_window_payload(
            window_seconds=60.0,
            lags_ms=[],
            request_window=RequestStats().drain(),
            pool=None,
            threadpool=None,
        )

        assert payload["pool_checked_out_max"] is None
        assert payload["threadpool_borrowed_max"] is None
        assert payload["loop_lag_p95_ms"] is None

    def test_payload_identifies_the_worker(self):
        payload = build_window_payload(
            window_seconds=60.0,
            lags_ms=[],
            request_window=RequestStats().drain(),
            pool=None,
            threadpool=None,
        )

        assert isinstance(payload["worker_pid"], int)


class TestConcurrencyProbeLoop:
    async def test_emits_one_log_line_per_window(self, caplog):
        caplog.set_level(logging.INFO, logger="baluhost.concurrency")

        task = asyncio.create_task(
            concurrency_probe_loop(interval_seconds=0.1, tick_seconds=0.01)
        )
        await asyncio.sleep(0.35)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        records = [r for r in caplog.records if r.name == "baluhost.concurrency"]
        assert len(records) >= 2, "mindestens zwei Fenster in 0,35 s bei 0,1 s Fenster"
        assert hasattr(records[0], "loop_lag_max_ms")
        assert hasattr(records[0], "req_in_flight_max")

    async def test_stops_promptly_on_cancel(self):
        task = asyncio.create_task(
            concurrency_probe_loop(interval_seconds=60, tick_seconds=0.01)
        )
        await asyncio.sleep(0.05)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    async def test_a_blocked_loop_shows_up_as_lag(self, caplog):
        """Der Kern der Messung: blockiert etwas den Loop, muss der Lag es zeigen."""
        import time as _time

        caplog.set_level(logging.INFO, logger="baluhost.concurrency")

        task = asyncio.create_task(
            concurrency_probe_loop(interval_seconds=0.3, tick_seconds=0.01)
        )
        await asyncio.sleep(0.02)
        _time.sleep(0.15)  # synchron blockieren, genau wie eine sync DB-Query
        await asyncio.sleep(0.35)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        records = [r for r in caplog.records if r.name == "baluhost.concurrency"]
        assert records, "kein Fenster emittiert"
        assert records[0].loop_lag_max_ms > 100, (
            f"150 ms Blockade nicht sichtbar: {records[0].loop_lag_max_ms} ms"
        )
```

- [ ] **Step 3: Run test to verify it fails**

```
cd backend
python -m pytest tests/core/test_concurrency_probe.py -v --no-cov
```

Erwartet: `ImportError: cannot import name 'build_window_payload'`

- [ ] **Step 4: Write minimal implementation**

An `backend/app/core/concurrency_probe.py` anhängen (Imports oben um `asyncio`, `logging`, `os`, `time` ergänzen):

```python
logger = logging.getLogger("baluhost.concurrency")


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
```

Die Message ist absichtlich für den Dev-Formatter lesbar, während `extra=payload` in Produktion (JSON-Formatter) die vollständigen Felder erzeugt. Der Dev-Formatter verwirft `extra` — deshalb stehen die drei wichtigsten Werte zusätzlich im Text.

- [ ] **Step 5: Run test to verify it passes**

```
cd backend
python -m pytest tests/core/test_concurrency_probe.py -v --no-cov
```

Erwartet: alle Tests PASS. Falls `test_a_blocked_loop_shows_up_as_lag` auf einer langsamen Maschine flackert: die 150-ms-Blockade und die 100-ms-Schwelle haben 50 ms Reserve — nicht die Schwelle senken, sondern prüfen, ob der Tick tatsächlich läuft.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/concurrency_probe.py backend/app/core/config.py backend/tests/core/test_concurrency_probe.py
git commit -m "feat(probe): event-loop lag probe and per-window structured report (#300)"
```

---

### Task 5: Verdrahtung im Lifespan

**Files:**
- Modify: `backend/app/core/lifespan.py` (in `_startup()`, ab Zeile 417)
- Test: `backend/tests/core/test_concurrency_probe_wiring.py`

**Interfaces:**
- Consumes: `concurrency_probe_loop()` aus Task 4, `_spawn_background()` aus `lifespan.py:64`
- Produces: ein Background-Task mit dem Namen `concurrency_probe`

- [ ] **Step 1: Write the failing test**

Erzeuge `backend/tests/core/test_concurrency_probe_wiring.py`:

```python
"""Die Probe muss im Lifespan hängen — und im Shutdown wieder verschwinden."""
from fastapi.testclient import TestClient

from app.core import lifespan as lifespan_module
from app.main import app


def _probe_tasks() -> list:
    return [
        task
        for task in lifespan_module._BACKGROUND_TASKS
        if task.get_name() == "concurrency_probe"
    ]


def test_probe_task_runs_while_the_app_is_up(client: TestClient):
    """Die `client`-Fixture betritt den TestClient-Kontext und fährt damit den
    echten Lifespan hoch."""
    tasks = _probe_tasks()

    assert len(tasks) == 1, "genau ein Probe-Task pro Worker"
    assert not tasks[0].done()


def test_probe_task_is_cancelled_on_shutdown():
    """Nach dem Verlassen des Kontexts darf kein Task zurückbleiben.

    Bewusst OHNE die `client`-Fixture: die verwaltet ihren TestClient-Kontext
    selbst, ein manuelles __exit__ würde ihn doppelt verlassen. Hier gehört
    der Kontext dem Test, also kann er ihn regulär schließen und danach prüfen.
    """
    with TestClient(app):
        tasks = _probe_tasks()
        assert len(tasks) == 1
        task = tasks[0]

    assert task.cancelled() or task.done()
    assert not _probe_tasks(), "_BACKGROUND_TASKS muss geleert sein"
```

- [ ] **Step 2: Run test to verify it fails**

```
cd backend
python -m pytest tests/core/test_concurrency_probe_wiring.py -v --no-cov
```

Erwartet: FAIL mit `assert len([]) == 1` — der Task existiert noch nicht.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/core/lifespan.py`, in `_startup()`, direkt **vor** dem Block „Start SmartDevice WebSocket bridge (primary worker only)" (aktuell Zeile 654):

```python
    # Concurrency-Probe (S1/#300): läuft auf JEDEM Worker, nicht nur dem
    # primären — der gesuchte Effekt (blockierter Event-Loop, Pool-Auslastung)
    # ist per Worker verschieden und wäre aus nur einem Prozess nicht ablesbar.
    if settings.concurrency_probe_enabled:
        from app.core.concurrency_probe import concurrency_probe_loop
        _spawn_background(concurrency_probe_loop(), "concurrency_probe")
        logger.info(
            "Concurrency probe started (interval=%ss)",
            settings.concurrency_probe_interval_seconds,
        )
```

- [ ] **Step 4: Run test to verify it passes**

```
cd backend
python -m pytest tests/core/test_concurrency_probe_wiring.py -v --no-cov
```

Erwartet: beide Tests PASS.

- [ ] **Step 5: Verify nothing else regressed**

```
cd backend
python -m pytest tests/core -q --no-cov
```

Erwartet: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/lifespan.py backend/tests/core/test_concurrency_probe_wiring.py
git commit -m "feat(probe): start the concurrency probe on every worker (#300)"
```

---

### Task 6: `baluhost_database_connections` befüllen

**Files:**
- Modify: `backend/app/api/routes/metrics.py:450-463` (`collect_database_metrics`)
- Test: `backend/tests/api/test_metrics_db_connections.py`

**Interfaces:**
- Consumes: `sample_pool()` aus Task 3
- Produces: nichts für spätere Tasks

Kontext: Die Gauge ist seit v1.2 deklariert (`metrics.py:255`) und in
`docs/monitoring/MONITORING.{en,de}.md:186` dokumentiert, wurde aber nie gesetzt.
Sie wird hier befüllt, weil es dieselbe Messung ist wie in Task 3. Die übrigen
11 toten Metriken sind [#494](https://github.com/Xveyn/BaluHost/issues/494) und
gehören **nicht** in diesen PR.

- [ ] **Step 1: Write the failing test**

Erzeuge `backend/tests/api/test_metrics_db_connections.py`:

```python
"""baluhost_database_connections war deklariert, aber nie gesetzt (#300/#494)."""
from app.api.routes.metrics import collect_database_metrics, registry


def test_database_connections_gauge_is_populated(db_session):
    collect_database_metrics(db_session)

    value = registry.get_sample_value("baluhost_database_connections")
    assert value is not None, "Gauge wurde nicht gesetzt"
    assert value >= 0


def test_collect_survives_a_pool_without_counters(db_session, monkeypatch):
    """Der StaticPool der Tests hat checkedout() nicht — das darf den
    kompletten Metrik-Endpoint nicht mitreißen."""
    monkeypatch.setattr(
        "app.api.routes.metrics.sample_pool", lambda engine: None
    )

    collect_database_metrics(db_session)  # darf nicht werfen
```

- [ ] **Step 2: Run test to verify it fails**

```
cd backend
python -m pytest tests/api/test_metrics_db_connections.py -v --no-cov
```

Erwartet: FAIL mit `assert None is not None` — „Gauge wurde nicht gesetzt".

- [ ] **Step 3: Write minimal implementation**

In `backend/app/api/routes/metrics.py` den Import ergänzen:

```python
from app.core.concurrency_probe import sample_pool
```

und `collect_database_metrics` erweitern:

```python
def collect_database_metrics(db: Session):
    """Collect database statistics."""
    try:
        from app.models.user import User

        # Count users by role
        admin_count = db.query(User).filter(User.role == 'admin').count()
        user_count = db.query(User).filter(User.role == 'user').count()

        users_total.labels(role='admin').set(admin_count)
        users_total.labels(role='user').set(user_count)

        # Connection-Pool-Auslastung (#300). Die Gauge war seit v1.2 deklariert,
        # wurde aber nie gesetzt — die Doku versprach sie trotzdem.
        from app.core.database import engine
        pool = sample_pool(engine)
        if pool is not None:
            database_connections.set(pool.checked_out)

    except Exception as e:
        logger.warning("Error collecting database metrics: %s", e)
```

- [ ] **Step 4: Run test to verify it passes**

```
cd backend
python -m pytest tests/api/test_metrics_db_connections.py -v --no-cov
```

Erwartet: beide Tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/metrics.py backend/tests/api/test_metrics_db_connections.py
git commit -m "fix(metrics): populate baluhost_database_connections from the pool (#300)"
```

---

### Task 7: Dokumentation und Abschluss-Gates

**Files:**
- Create: `docs/monitoring/CONCURRENCY_PROBE.md`
- Modify: `backend/app/middleware/CLAUDE.md` (Tabelle „Files" + Abschnitt „Adding Middleware")
- Modify: `backend/app/core/CLAUDE.md` (Tabelle „Files")

**Interfaces:**
- Consumes: alles aus Tasks 1-6
- Produces: nichts

- [ ] **Step 1: Write the operator guide**

Erzeuge `docs/monitoring/CONCURRENCY_PROBE.md`:

````markdown
# Concurrency-Probe (S1 / #300)

Temporäre Instrumentierung, die misst, wie stark synchrone DB-Arbeit den
Event-Loop blockiert. Die Zahlen begründen die Pool- und Threadpool-Grenzen
in PR2 — ohne sie wären die Grenzen geraten.

## Konfiguration

| Env-Variable | Default | Bedeutung |
|---|---|---|
| `CONCURRENCY_PROBE_ENABLED` | `true` | Probe an/aus |
| `CONCURRENCY_PROBE_INTERVAL_SECONDS` | `60` | Fensterlänge |

## Auslesen

Jeder Worker schreibt pro Fenster eine Zeile auf dem Logger
`baluhost.concurrency`. In Produktion ist das JSON:

```bash
journalctl -u baluhost-backend --since "-24h" -o cat \
  | jq -c 'select(.logger == "baluhost.concurrency")'
```

Die interessanten Felder:

| Feld | Bedeutung |
|---|---|
| `loop_lag_p95_ms`, `loop_lag_max_ms` | **Leitkennzahl.** Wie lange ein Task nicht drankam. Hohe Werte = blockierter Loop |
| `req_in_flight_max` | Gleichzeitige Requests im Worker — **untere Schranke**, siehe unten |
| `req_started`, `window_seconds` | Ankunftsrate = `req_started / window_seconds` |
| `req_duration_p95_ms` | Bedienzeit |
| `pool_checked_out_max`, `pool_open_max`, `pool_size`, `pool_max_overflow` | DB-Pool-Auslastung und Obergrenze |
| `pool_saturated_ticks` | Ticks, in denen der Pool voll ausgeschöpft war. `0` beweist, dass in diesem Fenster kein Checkout-Timeout möglich war |
| `threadpool_borrowed_max`, `threadpool_waiting_max` | anyio-Threadpool; `waiting > 0` heißt, sync Arbeit staut sich |
| `worker_pid` | Unterscheidet die 4 Worker |

## Warum `req_in_flight_max` nicht direkt für die Auslegung taugt

Solange die Handler den Loop blockieren, stauen sich neue Requests **vor** dem
Accept und werden nicht als „in flight" gezählt. Der Peak ist deshalb nach
unten verzerrt und nur als untere Schranke brauchbar.

Unverzerrt sind Ankunftsrate und Bedienzeit. Die Auslegung läuft über
Little's Law:

```
Nebenläufigkeit ≈ (req_started / window_seconds) × (req_duration_p95_ms / 1000)
```

Diese Zahl — nicht der beobachtete Peak — ist die Grundlage für
`DB_POOL_SIZE` / `DB_MAX_OVERFLOW` und die anyio-Token-Zahl in PR2.

## Kapazitätsgrenze, die eingehalten werden muss

```
4 Worker × (DB_POOL_SIZE + DB_MAX_OVERFLOW) + Sidecar-Bedarf < max_connections
```

Aktuell: 4 × (10 + 20) = 120 mögliche Verbindungen gegen ein ungetuntes
PostgreSQL-`max_connections` von 100. Drei weitere systemd-Units
(monitoring, scheduler, webdav) haben eigene Pools.

## Abbau

Die Probe ist als Diagnose gedacht, nicht als Dauerbetrieb. Nach dem
Nachher-Vergleich in PR2 entscheiden: behalten (dann in die reguläre
Monitoring-Doku überführen) oder entfernen.
````

- [ ] **Step 2: Update the middleware CLAUDE.md**

In `backend/app/middleware/CLAUDE.md` in die Tabelle „Files" aufnehmen:

```markdown
| `inflight.py` | Zählt laufende HTTP-Requests und ihre Gesamtdauer für die Concurrency-Probe (S1/#300). **Pure ASGI, kein `BaseHTTPMiddleware`** — sie soll Overhead messen, nicht erzeugen. Als letzte in `main.py` registriert und damit die äußerste Schicht | Alle HTTP-Requests |
```

Und den einleitenden Satz des Dokuments präzisieren, weil er nicht mehr für alle gilt — statt „Starlette `BaseHTTPMiddleware` classes applied to all requests":

```markdown
Middleware applied to all requests. Die meisten sind Starlette-`BaseHTTPMiddleware`;
`inflight.py` ist bewusst pure ASGI. Registriert in `main.py` — order matters.
```

- [ ] **Step 3: Update the core CLAUDE.md**

In `backend/app/core/CLAUDE.md` in die Tabelle „Files" aufnehmen:

```markdown
| `concurrency_probe.py` | Instrumentierung für S1/#300: Event-Loop-Lag, In-Flight-Requests, DB-Pool- und anyio-Threadpool-Auslastung. Ein Lifespan-Task pro Worker meldet alle 60 s ein Fenster auf dem Logger `baluhost.concurrency`. Siehe `docs/monitoring/CONCURRENCY_PROBE.md` |
```

- [ ] **Step 4: Run the full gates**

```
cd backend
python -m ruff check app tests
python -m pytest tests -q -x --no-cov
```

Erwartet: ruff ohne Befund; Suite grün. Bekannte Windows-Flakes (zwei
auth/permission-Delete-Tests, `os_sleep_inspector`-Subprozess-Tests) sind
vorbestehend und kein Ergebnis dieses PRs — falls sie auftreten, einzeln
nachfahren und im PR-Text benennen, nicht stillschweigend übergehen.

- [ ] **Step 5: Verify the probe actually emits in a running dev backend**

```
cd ..
python start_dev.py
```

In einem zweiten Terminal ein paar Requests absetzen, dann im Backend-Log nach
`concurrency window:` suchen. Erwartet: alle 60 s eine Zeile mit plausiblen
Werten (`loop_lag_p95` klein im Leerlauf, `req_started` > 0 nach den Requests).

Das ist der Beleg, dass die Probe im echten Prozess läuft — die Unit-Tests
prüfen nur die Bausteine.

- [ ] **Step 6: Commit and push**

```bash
git add docs/monitoring/CONCURRENCY_PROBE.md backend/app/middleware/CLAUDE.md backend/app/core/CLAUDE.md
git commit -m "docs(probe): operator guide and CLAUDE.md entries for the concurrency probe (#300)"
git push -u origin feat/s1-concurrency-probe
```

- [ ] **Step 7: Open the PR**

Den PR-Body in eine Datei schreiben und `gh pr create --body-file` nutzen —
Here-Strings scheitern in beiden Shells dieses Setups, und
`Set-Content -Encoding utf8` setzt ein BOM. Also mit einem Datei-Schreibwerkzeug
`pr-body.md` außerhalb des Repos anlegen:

```markdown
## Was das ist

PR 1 von 2 für **#300 (S1)**. Dieser PR ändert **kein** Route-Verhalten — er
misst nur. Der eigentliche Sweep (314 Handler von `async def` auf `def`) ist
PR 2 und folgt erst, wenn hier 3-7 Tage Messdaten aus dem Normalbetrieb
vorliegen.

Design: `docs/superpowers/specs/2026-07-30-s1-sync-sqlalchemy-event-loop-design.md`
Plan: `docs/superpowers/plans/2026-07-30-s1-pr1-concurrency-probe.md`

## Warum erst messen

Nach dem Sweep gilt pro Worker `min(anyio-Threadpool 40, Pool 10+20)`. Bei
4 Workern sind das bis zu 120 gleichzeitige PostgreSQL-Verbindungen — gegen
ein `max_connections`, das `06-postgresql.sh` nie tuned und das bei Debian
standardmäßig 100 ist. Die Grenzen in PR 2 müssen aus echten Zahlen kommen,
nicht aus einer Schätzung.

## Was gemessen wird

Ein Lifespan-Task pro Worker schreibt alle 60 s eine strukturierte Logzeile
auf dem Logger `baluhost.concurrency`:

- **`loop_lag_p95_ms` / `loop_lag_max_ms`** — die Leitkennzahl. Um wie viel ein
  `sleep(250ms)` seine Sollzeit überschreitet. Das ist der direkte Abdruck des
  Defekts aus #300 und der Vorher-Wert für den Abnahmevergleich in PR 2.
- `req_started`, `req_duration_p95_ms`, `req_in_flight_max`
- `pool_checked_out_max`, `pool_open_max`, `pool_saturated_ticks`
- `threadpool_borrowed_max`, `threadpool_waiting_max`

Auslesen und Interpretieren: `docs/monitoring/CONCURRENCY_PROBE.md`.

Wichtig für die spätere Auswertung: `req_in_flight_max` ist **nach unten
verzerrt**, weil sich Requests bei blockiertem Loop vor dem Accept stauen. Die
Auslegung läuft über Ankunftsrate × Bedienzeit (Little's Law), nicht über den
beobachteten Peak.

## Enthalten

- `middleware/inflight.py` — pure ASGI, bewusst **kein** `BaseHTTPMiddleware`
  (der Stack hat davon acht, K9/#334; ein Overhead-Messer darf ihn nicht
  vergrößern). Als letzte registriert = äußerste Schicht.
- `core/concurrency_probe.py` — Zustand, Sampler, Reporter.
- `core/lifespan.py` — Task über das vorhandene `_spawn_background()`, wird im
  Shutdown gecancelt (kein sechster unreferenzierter Loop, vgl. K2/#320).
- `baluhost_database_connections` wird endlich befüllt. Die Gauge war seit v1.2
  deklariert und dokumentiert, aber nie gesetzt. Die übrigen 11 toten Metriken
  sind #494 und bewusst **nicht** hier drin.

## Abschaltbar

`CONCURRENCY_PROBE_ENABLED=false`. Intervall über
`CONCURRENCY_PROBE_INTERVAL_SECONDS`.

## Getestet

- Neue Unit-Tests für Perzentile, Request-Zähler, Pool-/Threadpool-Sampler
  (inkl. Degradation bei `StaticPool`/`NullPool`), Payload-Kollisionsfreiheit
  gegen `LogRecord`-Attribute, Fenster-Emission und Cancel-Verhalten.
- Ein Test blockiert den Loop synchron für 150 ms und prüft, dass der Lag es
  sichtbar macht — sonst misst die Probe nichts.
- Volle Backend-Suite und ruff grün.
- Im laufenden Dev-Backend verifiziert, dass die Zeile tatsächlich erscheint.
```

Dann:

```bash
gh pr create --base main --head feat/s1-concurrency-probe \
  --title "feat(probe): concurrency instrumentation for S1, PR 1 of 2 (#300)" \
  --body-file <pfad-zu>/pr-body.md
```

---

## Nach dem Merge

Deployen und **3-7 Tage Normalbetrieb** abwarten. Danach die Fenster auswerten
und erst dann den Plan für PR2 schreiben. Für die Auswertung mindestens
festhalten:

- `loop_lag_p95_ms` / `loop_lag_max_ms` als Baseline für den Nachher-Vergleich
- Ankunftsrate und `req_duration_p95_ms` pro Worker → Little's Law
- `pool_checked_out_max` und `threadpool_waiting_max` als Realitätsabgleich

Diese Zahlen gehören als Kommentar an [#300](https://github.com/Xveyn/BaluHost/issues/300),
damit die Grenzwerte in PR2 nachvollziehbar begründet sind.
