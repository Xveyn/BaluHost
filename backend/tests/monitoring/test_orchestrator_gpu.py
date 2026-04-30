"""GPU integration in MonitoringOrchestrator."""
import asyncio
from unittest.mock import MagicMock

import pytest

from app.services.monitoring.orchestrator import MonitoringOrchestrator
from app.services.monitoring.gpu_collector import GpuMetricCollector


def test_orchestrator_has_gpu_collector():
    o = MonitoringOrchestrator()
    assert hasattr(o, "gpu_collector")
    assert isinstance(o.gpu_collector, GpuMetricCollector)


def test_sample_once_skips_when_no_gpu():
    """With detected=False, the GPU collector must not write to DB or raise."""
    o = MonitoringOrchestrator()

    class _Fake:
        detected = False
        def read_sample(self):
            raise AssertionError("must not be called")

    o.gpu_collector.backend = _Fake()

    async def _run():
        await o._sample_once()

    asyncio.run(_run())  # should complete without exception


def test_get_gpu_current_returns_none_when_no_data():
    o = MonitoringOrchestrator()
    # Fresh orchestrator — no samples in buffer
    assert o.get_gpu_current() is None


def test_get_gpu_history_returns_list():
    o = MonitoringOrchestrator()
    history = o.get_gpu_history()
    assert isinstance(history, list)
