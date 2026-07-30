"""Tests für die Concurrency-Probe (S1/#300, PR1)."""
import logging

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool, StaticPool

from app.core.concurrency_probe import (
    PoolSample,
    RequestStats,
    ThreadPoolSample,
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


class TestSampleThreadPool:
    async def test_reads_the_anyio_limiter(self):
        sample = sample_threadpool()

        assert isinstance(sample, ThreadPoolSample)
        assert sample.total_tokens > 0
        assert sample.borrowed >= 0
        assert sample.waiting >= 0

    def test_returns_none_outside_an_event_loop(self):
        assert sample_threadpool() is None
