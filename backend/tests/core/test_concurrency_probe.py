"""Tests für die Concurrency-Probe (S1/#300, PR1)."""
import asyncio
import logging
import threading

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool, StaticPool

from app.core.concurrency_probe import (
    PoolCheckoutTracker,
    PoolSample,
    PoolWindow,
    RequestStats,
    ThreadPoolSample,
    build_window_payload,
    concurrency_probe_loop,
    get_pool_tracker,
    get_request_stats,
    percentile,
    sample_pool,
    sample_threadpool,
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

    def test_p95_is_the_high_tail_not_the_median(self):
        """`duration_p95_ms` wird von der Auslegungsmethode gelesen. Ohne diese
        Zusage bliebe ein vertauschtes p50/p95 oder ein `q=0.50` unbemerkt."""
        stats = RequestStats()
        for ms in range(1, 101):  # 1..100 ms
            stats.record_start()
            stats.record_end(ms / 1000.0)

        window = stats.drain()
        assert window.duration_p50_ms == pytest.approx(50.0)
        assert window.duration_p95_ms == pytest.approx(95.0)
        assert window.duration_max_ms == pytest.approx(100.0)

    def test_mean_duration_is_reported(self):
        """Little's Law ist auf der MITTLEREN Bedienzeit definiert — ohne
        Mittelwert ist die dokumentierte Methode nicht ausführbar."""
        stats = RequestStats()
        for seconds in (0.001, 0.002, 0.006):
            stats.record_start()
            stats.record_end(seconds)

        window = stats.drain()
        assert window.duration_mean_ms == pytest.approx(3.0)

    def test_mean_covers_all_requests_not_just_the_quantile_buffer(self):
        """Der Quantil-Puffer ist gedeckelt; der Mittelwert darf es nicht sein,
        sonst wäre er der Mittelwert der letzten N statt des Fensters."""
        stats = RequestStats(max_samples=10)
        for _ in range(90):
            stats.record_start()
            stats.record_end(0.001)  # 1 ms
        for _ in range(10):
            stats.record_start()
            stats.record_end(0.011)  # 11 ms — füllt den Puffer allein

        window = stats.drain()
        assert window.completed == 100
        # Mittelwert über alle 100: (90*1 + 10*11) / 100 = 2.0
        assert window.duration_mean_ms == pytest.approx(2.0)
        # Nur über den Puffer wären es 11.0 — der Unterschied ist der Test.
        assert window.duration_p50_ms == pytest.approx(11.0)

    def test_mean_resets_with_the_window(self):
        stats = RequestStats()
        stats.record_start()
        stats.record_end(0.010)
        stats.drain()

        assert stats.drain().duration_mean_ms is None

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

    def test_logs_on_exception_in_pool_methods(self, caplog):
        """When pool methods raise, sample_pool logs at debug level and returns None."""

        class FaultyPool:
            def checkedout(self):
                raise RuntimeError("Simulated pool error")

            def overflow(self):
                raise RuntimeError("Simulated pool error")

            def checkedin(self):
                raise RuntimeError("Simulated pool error")

            def size(self):
                raise RuntimeError("Simulated pool error")

        class FaultyEngine:
            pool = FaultyPool()

        caplog.set_level(logging.DEBUG, logger="baluhost.concurrency")
        result = sample_pool(FaultyEngine())

        assert result is None
        assert any(
            "Failed to sample pool" in record.message
            for record in caplog.records
            if record.name == "baluhost.concurrency"
        )


class _ExplodingLock:
    """Simuliert einen Tracker, der beim Zählen wirft."""

    def __enter__(self):
        raise RuntimeError("tracker is broken")

    def __exit__(self, *_exc):
        return False


class TestPoolCheckoutTracker:
    """Die Checkout-Buchführung ersetzt das Point-Sampling der Belegung.

    Warum: einen Checkout hält ein nicht-awaitender `async def` Handler,
    während der Event-Loop blockiert ist — der Sampler-Task kommt dann gar
    nicht dran. Der Listener läuft im Thread des Checkouts und sieht jeden.
    """

    def test_counts_checkouts_and_the_high_water_mark(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path / 'probe.db'}")
        tracker = PoolCheckoutTracker()
        assert tracker.attach(engine) is True

        first = engine.connect()
        second = engine.connect()
        first.close()
        second.close()
        third = engine.connect()
        third.close()

        window = tracker.drain()
        assert window.checkouts == 3
        assert window.in_use_max == 2

    async def test_sees_what_point_sampling_structurally_cannot(self, tmp_path):
        """Der Kern von C1: ein Sampler auf dem Loop sieht 0, der Tracker 1.

        Nachgestellt wird exakt das Muster der 314 nicht-awaitenden Handler:
        Verbindung nehmen, synchron arbeiten, freigeben — ohne den Loop
        zwischendurch freizugeben.
        """
        import time as _time

        engine = create_engine(f"sqlite:///{tmp_path / 'probe.db'}")
        tracker = PoolCheckoutTracker()
        assert tracker.attach(engine) is True

        sampled: list[int] = []

        async def sampler() -> None:
            while True:
                point = sample_pool(engine)
                if point is not None:
                    sampled.append(point.checked_out)
                await asyncio.sleep(0.001)

        task = asyncio.create_task(sampler())
        await asyncio.sleep(0.02)  # Sampler läuft nachweislich

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            _time.sleep(0.05)  # Loop blockiert, Verbindung gehalten

        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        window = tracker.drain()
        assert window.checkouts == 1
        assert window.in_use_max == 1
        assert sampled, "Sampler lief nicht — der Vergleich wäre wertlos"
        assert max(sampled) == 0, (
            "Point-Sampling hat den Checkout gesehen — dann misst dieser Test "
            "nicht mehr das Problem, das die Buchführung löst"
        )

    def test_saturation_events_count_checkouts_taking_the_last_connection(
        self, tmp_path
    ):
        engine = create_engine(
            f"sqlite:///{tmp_path / 'probe.db'}", pool_size=1, max_overflow=1
        )
        tracker = PoolCheckoutTracker()
        assert tracker.attach(engine) is True

        first = engine.connect()  # 1 von 2 — keine Sättigung
        second = engine.connect()  # 2 von 2 — Sättigung
        first.close()
        second.close()
        third = engine.connect()  # wieder 1 von 2
        third.close()

        window = tracker.drain()
        assert window.checkouts == 3
        assert window.saturation_events == 1

    def test_saturation_is_none_when_the_ceiling_is_unknown(self):
        """StaticPool (Testsuite) kennt kein max_overflow — dann wird über
        Sättigung nichts behauptet. Gezählt wird trotzdem: die Events feuern
        auch dort, wo `sample_pool()` mangels Zählern None liefert."""
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        tracker = PoolCheckoutTracker()
        assert tracker.attach(engine) is True

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        assert sample_pool(engine) is None, "Point-Sampling ist hier blind"
        window = tracker.drain()
        assert window.checkouts == 1
        assert window.saturation_events is None

    def test_attach_is_idempotent(self, tmp_path):
        """Ein zweiter Listener-Satz würde jeden Checkout doppelt zählen."""
        engine = create_engine(f"sqlite:///{tmp_path / 'probe.db'}")
        tracker = PoolCheckoutTracker()

        assert tracker.attach(engine) is True
        assert tracker.attach(engine) is False

        with engine.connect():
            pass

        assert tracker.drain().checkouts == 1

    def test_drain_resets_counters_but_keeps_a_held_connection_visible(
        self, tmp_path
    ):
        engine = create_engine(f"sqlite:///{tmp_path / 'probe.db'}")
        tracker = PoolCheckoutTracker()
        tracker.attach(engine)

        conn = engine.connect()
        first = tracker.drain()
        second = tracker.drain()

        assert first.checkouts == 1
        assert first.in_use_max == 1
        assert second.checkouts == 0, "Zähler muss zurückgesetzt sein"
        assert second.in_use_max == 1, "gehaltene Verbindung bleibt sichtbar"

        conn.close()

    def test_counts_concurrent_checkouts_from_other_threads(self, tmp_path):
        """Checkouts passieren auch in Threadpool-Threads — der Zähler muss
        thread-sicher sein und gleichzeitige Belegung als solche zeigen."""
        engine = create_engine(
            f"sqlite:///{tmp_path / 'probe.db'}", pool_size=5, max_overflow=5
        )
        tracker = PoolCheckoutTracker()
        tracker.attach(engine)

        barrier = threading.Barrier(4)
        errors: list[BaseException] = []

        def hold() -> None:
            try:
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                    barrier.wait(timeout=10)
            except BaseException as exc:  # pragma: no cover - Diagnose
                errors.append(exc)

        threads = [threading.Thread(target=hold) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)

        assert not errors, f"Worker-Thread scheiterte: {errors}"
        window = tracker.drain()
        assert window.checkouts == 4
        assert window.in_use_max == 4

    def test_a_failing_listener_never_propagates_into_a_checkout(
        self, tmp_path, caplog
    ):
        """Die gefährlichste Stelle des Branches: der Listener hängt in
        SQLAlchemys Checkout-Pfad. Würde er werfen, bräche JEDE
        Datenbankoperation der Anwendung."""
        engine = create_engine(f"sqlite:///{tmp_path / 'probe.db'}")
        tracker = PoolCheckoutTracker()
        assert tracker.attach(engine) is True

        caplog.set_level(logging.DEBUG, logger="baluhost.concurrency")
        tracker._lock = _ExplodingLock()  # jeder Listener-Aufruf wirft jetzt

        with engine.connect() as conn:
            assert conn.execute(text("SELECT 1")).scalar() == 1
        # Zweiter Durchlauf: auch der Checkin-Listener ist schon geplatzt.
        with engine.connect() as conn:
            assert conn.execute(text("SELECT 1")).scalar() == 1

        assert any(
            "Pool checkout listener failed" in record.message
            for record in caplog.records
            if record.name == "baluhost.concurrency"
        ), "Fehler wurde nicht einmal auf DEBUG sichtbar"

        tracker._lock = threading.Lock()
        assert tracker.drain().checkouts == 0, "kaputter Tracker zählt nichts"

    def test_listeners_survive_pool_replacement(self, tmp_path):
        """`engine.dispose()` ersetzt den Pool (passiert bei recycle/pre-ping).
        Hingen die Listener am Pool statt am Engine, stünde die Buchführung
        danach still auf null — ein Instrument, das aufhört zu messen, ohne es
        zu sagen."""
        engine = create_engine(f"sqlite:///{tmp_path / 'probe.db'}")
        tracker = PoolCheckoutTracker()
        tracker.attach(engine)

        with engine.connect():
            pass
        tracker.drain()
        engine.dispose()

        with engine.connect():
            pass

        assert tracker.drain().checkouts == 1

    def test_no_drift_when_a_connection_is_invalidated(self, tmp_path):
        """Ein Checkin, das ausbleibt, hebt den In-Use-Zähler dauerhaft an und
        vererbt den Fehler an jedes spätere Fenster."""
        engine = create_engine(f"sqlite:///{tmp_path / 'probe.db'}")
        tracker = PoolCheckoutTracker()
        tracker.attach(engine)

        with engine.connect() as conn:
            conn.invalidate()
        tracker.drain()

        assert tracker.drain().in_use_max == 0, "Verbindung blieb als belegt hängen"

    def test_attach_survives_an_engine_without_a_pool(self):
        """Die Registrierung selbst darf den Start nicht kippen."""

        class NotAnEngine:
            pool = None

        tracker = PoolCheckoutTracker()
        assert tracker.attach(NotAnEngine()) is False

    def test_get_pool_tracker_is_a_singleton(self):
        assert get_pool_tracker() is get_pool_tracker()


class TestSampleThreadPool:
    async def test_reads_the_anyio_limiter(self):
        sample = sample_threadpool()

        assert isinstance(sample, ThreadPoolSample)
        assert sample.total_tokens > 0
        assert sample.borrowed >= 0
        assert sample.waiting >= 0

    def test_returns_none_outside_an_event_loop(self):
        assert sample_threadpool() is None


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

    def test_pool_accounting_is_carried_through(self):
        payload = build_window_payload(
            window_seconds=60.0,
            lags_ms=[],
            request_window=RequestStats().drain(),
            pool=None,
            threadpool=None,
            pool_window=PoolWindow(
                checkouts=421, in_use_max=9, saturation_events=17
            ),
        )

        assert payload["pool_checkouts"] == 421
        assert payload["pool_in_use_max"] == 9
        assert payload["pool_saturation_events"] == 17

    def test_unknown_pool_ceiling_reports_no_saturation_claim(self):
        payload = build_window_payload(
            window_seconds=60.0,
            lags_ms=[],
            request_window=RequestStats().drain(),
            pool=None,
            threadpool=None,
            pool_window=PoolWindow(
                checkouts=3, in_use_max=1, saturation_events=None
            ),
        )

        assert payload["pool_checkouts"] == 3
        assert payload["pool_saturation_events"] is None, (
            "ohne bekannte Obergrenze darf keine 0 behauptet werden"
        )

    def test_mean_duration_reaches_the_payload(self):
        """Die dokumentierte Auslegungsformel liest genau dieses Feld."""
        stats = RequestStats()
        for seconds in (0.002, 0.004):
            stats.record_start()
            stats.record_end(seconds)

        payload = build_window_payload(
            window_seconds=60.0,
            lags_ms=[],
            request_window=stats.drain(),
            pool=None,
            threadpool=None,
        )

        assert payload["req_duration_mean_ms"] == pytest.approx(3.0)

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

        assert payload["pool_in_use_max"] is None
        assert payload["pool_checkouts"] is None
        assert payload["pool_open_max"] is None
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

    async def test_interval_falls_back_to_the_configured_setting(self, caplog):
        """`interval_seconds=None` ist der einzige Produktionspfad — im
        Lifespan wird `concurrency_probe_loop()` ohne Argument gestartet.
        Käme dabei nicht der Settings-Wert an, liefe die Probe mit einer
        anderen Fensterlänge als dokumentiert."""
        from app.core.config import settings as app_settings

        caplog.set_level(logging.INFO, logger="baluhost.concurrency")

        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(app_settings, "concurrency_probe_interval_seconds", 0.1)
            task = asyncio.create_task(
                concurrency_probe_loop(interval_seconds=None, tick_seconds=0.01)
            )
            await asyncio.sleep(0.35)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        records = [r for r in caplog.records if r.name == "baluhost.concurrency"]
        assert len(records) >= 2, (
            "Bei Default 60s käme kein Fenster — der Settings-Wert wurde nicht gelesen"
        )
        assert records[0].window_seconds < 1.0

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

    async def test_high_water_marks_do_not_survive_into_the_next_window(self, caplog):
        """Der primäre Risikopunkt der Aufgabe: überlebt ein Accumulator das
        Fenster-Ende, vererbt jedes spätere Fenster den ersten Peak weiter —
        die Zahlen wären dauerhaft zu hoch (Richtung Über-Provisionierung).

        Der Loop liest das Modul-Singleton, deshalb `get_request_stats()`
        statt einer eigenen `RequestStats()`-Instanz. Der In-Flight-Zähler
        wird bewusst noch innerhalb von Fenster 1 wieder auf 0 zurückgeführt,
        damit am Fenster-Ende kein Live-Wert übrig bleibt, der die Aussage
        verwässert.
        """
        import time as _time

        caplog.set_level(logging.INFO, logger="baluhost.concurrency")
        stats = get_request_stats()

        task = asyncio.create_task(
            concurrency_probe_loop(interval_seconds=0.2, tick_seconds=0.01)
        )
        await asyncio.sleep(0.02)

        # Fenster 1: In-Flight-Peak erzeugen ...
        stats.record_start()
        stats.record_start()
        stats.record_start()
        # 150 ms wie im Schwestertest: auf dem geteilten ci-sandbox-Runner
        # kann die Grundlast von Fenster 2 schon 15-30 ms Lag erzeugen — ein
        # 50-ms-Block ließe den Vergleich mehrdeutig werden.
        _time.sleep(0.15)  # ... und gleichzeitig Loop-Lag erzeugen
        # ... und noch innerhalb von Fenster 1 wieder auf 0 zurückführen.
        stats.record_end(0.001)
        stats.record_end(0.001)
        stats.record_end(0.001)

        # Zwei weitere Fenster ohne jede Last durchlaufen lassen.
        await asyncio.sleep(0.45)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        records = [r for r in caplog.records if r.name == "baluhost.concurrency"]
        assert len(records) >= 2, "Test braucht mindestens zwei Fenster"

        assert records[0].req_in_flight_max >= 3, (
            "Fenster 1 muss den erzeugten Peak zeigen"
        )
        assert records[1].req_in_flight_max < records[0].req_in_flight_max, (
            "Fenster 2 erbt den In-Flight-Peak aus Fenster 1 — Reset fehlt"
        )

        assert records[1].loop_lag_max_ms < records[0].loop_lag_max_ms, (
            "Fenster 2 erbt den Loop-Lag-Peak aus Fenster 1 — Reset fehlt"
        )
