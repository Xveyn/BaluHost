"""Tests for NVIDIA GPU power backend (nvidia-smi wrapper)."""
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from app.schemas.gpu_power import (
    GpuPowerConfig,
    GpuPowerState,
    NvidiaStateConfig,
)
from app.services.power.gpu.nvidia_backend import NvidiaGpuPowerBackend


def _mock_run(stdout: str = "", returncode: int = 0):
    result = MagicMock()
    result.stdout = stdout
    result.returncode = returncode
    return result


@pytest.fixture(autouse=True)
def _stub_nvidia_smi_on_path():
    # Ensure detection logic proceeds past `shutil.which` even on CI runners
    # where nvidia-smi is not installed. Tests drive behavior via subprocess.run patches.
    with patch("app.services.power.gpu.nvidia_backend.shutil.which", return_value="/usr/bin/nvidia-smi"):
        yield


def test_not_detected_when_nvidia_smi_missing():
    with patch("subprocess.run", side_effect=FileNotFoundError):
        backend = NvidiaGpuPowerBackend()
        assert backend.detected is False


def test_not_detected_when_no_gpus():
    with patch("subprocess.run", return_value=_mock_run(stdout="\n")):
        backend = NvidiaGpuPowerBackend()
        assert backend.detected is False


def test_detected_with_one_gpu():
    list_out = "GPU 0: NVIDIA GeForce RTX 4080 (UUID: GPU-...)\n"
    range_out = "210, 2505, 100, 320, 320\n"
    with patch("subprocess.run", side_effect=[
        _mock_run(stdout=list_out),  # nvidia-smi -L
        _mock_run(stdout=range_out),  # range query
        _mock_run(stdout=""),  # persistence-mode set
    ]):
        backend = NvidiaGpuPowerBackend()
        assert backend.detected is True
        assert backend.vendor == "nvidia"


def test_capabilities_seeded_from_card():
    list_out = "GPU 0: NVIDIA GeForce RTX 4080\n"
    range_out = "210, 2505, 100, 320, 320\n"
    with patch("subprocess.run", side_effect=[
        _mock_run(stdout=list_out),
        _mock_run(stdout=range_out),
        _mock_run(stdout=""),
    ]):
        backend = NvidiaGpuPowerBackend()
        caps = backend.capabilities()
        assert caps.nvidia_min_clock_mhz == 210
        assert caps.nvidia_max_clock_mhz == 2505
        assert caps.nvidia_min_power_watts == 100
        assert caps.nvidia_max_power_watts == 320
        assert caps.nvidia_default_power_watts == 320


@pytest.mark.asyncio
async def test_apply_active_resets_clocks():
    list_out = "GPU 0: NVIDIA GeForce RTX 4080\n"
    range_out = "210, 2505, 100, 320, 320\n"
    apply_calls = []

    def fake_run(args, **kwargs):
        apply_calls.append(args)
        return _mock_run()

    with patch("subprocess.run", side_effect=[
        _mock_run(stdout=list_out),
        _mock_run(stdout=range_out),
        _mock_run(stdout=""),
    ]):
        backend = NvidiaGpuPowerBackend()

    with patch("subprocess.run", side_effect=fake_run):
        ok, err = await backend.apply_state(GpuPowerState.ACTIVE, GpuPowerConfig())
        assert ok is True
        # Active default: -rgc + reset power limit
        assert any("-rgc" in " ".join(a) for a in apply_calls)


@pytest.mark.asyncio
async def test_apply_deep_idle_locks_clocks():
    list_out = "GPU 0: NVIDIA GeForce RTX 4080\n"
    range_out = "210, 2505, 100, 320, 320\n"
    apply_calls = []

    def fake_run(args, **kwargs):
        apply_calls.append(args)
        return _mock_run()

    with patch("subprocess.run", side_effect=[
        _mock_run(stdout=list_out),
        _mock_run(stdout=range_out),
        _mock_run(stdout=""),
    ]):
        backend = NvidiaGpuPowerBackend()

    config = GpuPowerConfig(
        nvidia_deep_idle=NvidiaStateConfig(
            min_clock_mhz=210,
            max_clock_mhz=210,
            power_limit_watts=100,
        )
    )

    with patch("subprocess.run", side_effect=fake_run):
        ok, err = await backend.apply_state(GpuPowerState.DEEP_IDLE, config)
        assert ok is True
        joined = [" ".join(a) for a in apply_calls]
        assert any("-lgc 210,210" in c for c in joined)
        assert any("-pl 100" in c for c in joined)


@pytest.mark.asyncio
async def test_apply_returns_error_on_subprocess_failure():
    list_out = "GPU 0: NVIDIA GeForce RTX 4080\n"
    range_out = "210, 2505, 100, 320, 320\n"

    with patch("subprocess.run", side_effect=[
        _mock_run(stdout=list_out),
        _mock_run(stdout=range_out),
        _mock_run(stdout=""),
    ]):
        backend = NvidiaGpuPowerBackend()

    with patch("subprocess.run", return_value=_mock_run(returncode=1, stdout="permission denied")):
        ok, err = await backend.apply_state(GpuPowerState.DEEP_IDLE, GpuPowerConfig())
        assert ok is False
        assert err is not None
