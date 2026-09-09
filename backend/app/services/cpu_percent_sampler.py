"""CPU usage sampling with a per-consumer reference point (issue #600).

`psutil.cpu_percent(interval=None)` keeps **one** reference point per process
and returns the load since the last call *from anywhere* in it. The backend had
four independent callers sharing it — two of them (`system.py`, `metrics.py`)
blocking on `interval=0.1` from request paths, which silently reset the
reference point for the telemetry loop whose value drives the sleep decision.
A `/api/system/info` request landing just before a telemetry tick left that tick
measuring a millisecond-wide window.

Each consumer holds its own `CpuPercentSampler` here, so no call can affect
another. The arithmetic mirrors psutil's own (`_cpu_busy_time` /
`_cpu_tot_time`) so the reported numbers stay comparable to what the app
reported before:

- guest and guest_nice are subtracted from the total (Linux counts them inside
  user/nice already, so leaving them in would double-count),
- idle and iowait are not busy.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Optional

import psutil

logger = logging.getLogger(__name__)

TimesProvider = Callable[[], object]


def _total_time(times) -> float:
    """Total CPU time, with Linux' double-counted guest time removed."""
    total = float(sum(times))
    total -= float(getattr(times, "guest", 0.0) or 0.0)
    total -= float(getattr(times, "guest_nice", 0.0) or 0.0)
    return total


def _busy_time(times) -> float:
    """Time the CPU actually spent working."""
    busy = _total_time(times)
    busy -= float(getattr(times, "idle", 0.0) or 0.0)
    busy -= float(getattr(times, "iowait", 0.0) or 0.0)
    return busy


def _percent_between(previous, current) -> float:
    """Busy share of the interval between two readings, in percent.

    Returns 0.0 when no time elapsed or the counters moved backwards — the
    latter is reachable across a suspend/resume, and a negative percentage
    would be worse than admitting we cannot tell.
    """
    total_delta = _total_time(current) - _total_time(previous)
    busy_delta = _busy_time(current) - _busy_time(previous)
    if total_delta <= 0 or busy_delta < 0:
        return 0.0
    return min(100.0, max(0.0, (busy_delta / total_delta) * 100.0))


class CpuPercentSampler:
    """CPU load since *this* sampler's previous call.

    Give every consumer its own instance. Sharing one would recreate exactly
    the problem this module exists to solve.
    """

    def __init__(self, times_provider: TimesProvider = psutil.cpu_times) -> None:
        self._times_provider = times_provider
        self._previous = None

    def sample(self) -> Optional[float]:
        """Percent since the last call, or None on the very first one.

        None means "no reference point yet", not "zero load" — callers must not
        collapse the two, or a fresh process looks fully idle for one tick.
        """
        current = self._times_provider()
        previous, self._previous = self._previous, current
        if previous is None:
            return None
        return _percent_between(previous, current)


def measure_cpu_percent(
    interval: float,
    times_provider: TimesProvider = psutil.cpu_times,
    sleeper: Callable[[float], None] = time.sleep,
) -> float:
    """Blocking measurement over *interval* seconds, self-contained.

    For request paths that need an answer right now and have no earlier
    reading to compare against. Holds no state, so it cannot disturb any
    sampler — which is precisely what `psutil.cpu_percent(interval=0.1)` did.
    """
    before = times_provider()
    sleeper(interval)
    after = times_provider()
    return _percent_between(before, after)
