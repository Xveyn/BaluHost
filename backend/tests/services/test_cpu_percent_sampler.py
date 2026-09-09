"""Tests for the per-consumer CPU sampler (issue #600).

The point of the module is that two consumers do NOT influence each other —
`psutil.cpu_percent(interval=None)` keeps ONE reference point per process, so
four callers were resetting it under each other. `test_two_samplers_are_independent`
is the regression test for exactly that.
"""
from collections import namedtuple

import pytest

from app.services.cpu_percent_sampler import CpuPercentSampler, measure_cpu_percent

# Mirrors psutil's Linux scputimes so `sum(times)` and the guest/iowait fields
# behave like the real thing.
Times = namedtuple(
    "Times",
    "user nice system idle iowait irq softirq steal guest guest_nice",
)


def _t(user=0.0, idle=0.0, iowait=0.0, guest=0.0, guest_nice=0.0, nice=0.0):
    return Times(user, nice, 0.0, idle, iowait, 0.0, 0.0, 0.0, guest, guest_nice)


class _FakeClock:
    """Hands out a scripted sequence of cpu_times() readings."""

    def __init__(self, *readings):
        self._readings = list(readings)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self._readings.pop(0)


class TestSample:
    def test_first_sample_has_no_reference_point(self):
        sampler = CpuPercentSampler(times_provider=_FakeClock(_t(user=10, idle=90)))
        assert sampler.sample() is None

    def test_second_sample_is_the_delta_since_the_first(self):
        clock = _FakeClock(_t(user=10, idle=90), _t(user=35, idle=165))
        sampler = CpuPercentSampler(times_provider=clock)
        sampler.sample()
        # 25 busy of 100 total elapsed
        assert sampler.sample() == pytest.approx(25.0)

    def test_fully_busy_is_100(self):
        clock = _FakeClock(_t(user=0, idle=0), _t(user=50, idle=0))
        sampler = CpuPercentSampler(times_provider=clock)
        sampler.sample()
        assert sampler.sample() == pytest.approx(100.0)

    def test_fully_idle_is_zero(self):
        clock = _FakeClock(_t(user=0, idle=0), _t(user=0, idle=50))
        sampler = CpuPercentSampler(times_provider=clock)
        sampler.sample()
        assert sampler.sample() == pytest.approx(0.0)

    def test_iowait_does_not_count_as_busy(self):
        """Matches psutil: iowait is time the CPU does nothing."""
        clock = _FakeClock(_t(user=0, idle=0, iowait=0), _t(user=25, idle=25, iowait=50))
        sampler = CpuPercentSampler(times_provider=clock)
        sampler.sample()
        assert sampler.sample() == pytest.approx(25.0)

    def test_guest_time_is_excluded_from_the_total(self):
        """Matches psutil on Linux: guest time is already counted inside user."""
        clock = _FakeClock(
            _t(user=0, idle=0, guest=0),
            _t(user=50, idle=50, guest=20),
        )
        sampler = CpuPercentSampler(times_provider=clock)
        sampler.sample()
        # total = 120 - 20 guest = 100; busy = 100 - 50 idle = 50
        assert sampler.sample() == pytest.approx(50.0)

    def test_no_elapsed_time_yields_zero_instead_of_dividing_by_zero(self):
        reading = _t(user=10, idle=90)
        clock = _FakeClock(reading, reading)
        sampler = CpuPercentSampler(times_provider=clock)
        sampler.sample()
        assert sampler.sample() == 0.0

    def test_counter_going_backwards_yields_zero(self):
        """A suspend/resume can make the accounting look like it moved back."""
        clock = _FakeClock(_t(user=100, idle=100), _t(user=10, idle=10))
        sampler = CpuPercentSampler(times_provider=clock)
        sampler.sample()
        assert sampler.sample() == 0.0

    def test_two_samplers_are_independent(self):
        """The whole reason this module exists (issue #600).

        With psutil's shared reference point, B's read would reset A's, and A's
        next sample would cover a near-zero window. Each sampler must keep its
        own previous reading.
        """
        readings = [
            _t(user=0, idle=0),      # A primes
            _t(user=0, idle=0),      # B primes
            _t(user=10, idle=10),    # B samples: 50% over its own window
            _t(user=10, idle=10),    # A samples: must ALSO see its full window
        ]
        shared = _FakeClock(*readings)
        a = CpuPercentSampler(times_provider=shared)
        b = CpuPercentSampler(times_provider=shared)

        a.sample()
        b.sample()
        assert b.sample() == pytest.approx(50.0)
        assert a.sample() == pytest.approx(50.0)


class TestMeasureBlocking:
    def test_measures_across_the_interval(self):
        clock = _FakeClock(_t(user=0, idle=0), _t(user=30, idle=70))
        slept = []
        value = measure_cpu_percent(
            0.1, times_provider=clock, sleeper=slept.append
        )
        assert value == pytest.approx(30.0)
        assert slept == [0.1]

    def test_does_not_disturb_a_samplers_reference_point(self):
        """The blocking call is what poisoned the non-blocking ones before."""
        readings = [
            _t(user=0, idle=0),      # sampler primes
            _t(user=5, idle=5),      # blocking measure start
            _t(user=10, idle=10),    # blocking measure end
            _t(user=20, idle=20),    # sampler samples over ITS window
        ]
        clock = _FakeClock(*readings)
        sampler = CpuPercentSampler(times_provider=clock)
        sampler.sample()
        measure_cpu_percent(0.1, times_provider=clock, sleeper=lambda _s: None)
        assert sampler.sample() == pytest.approx(50.0)
