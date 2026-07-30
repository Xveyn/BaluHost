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
