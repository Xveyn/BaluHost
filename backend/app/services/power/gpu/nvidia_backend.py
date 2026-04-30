"""NVIDIA GPU power backend via nvidia-smi.

Required commands (all use list-args, never shell=True):
- `nvidia-smi -L`                                    : list GPUs
- `nvidia-smi --query-gpu=... --format=csv,noheader,nounits` : capabilities
- `nvidia-smi -pm 1`                                 : enable persistence mode
- `nvidia-smi -lgc <min>,<max>` / `-rgc`             : lock/reset clocks
- `nvidia-smi -pl <watts>`                           : power limit
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
from typing import List, Optional, Tuple

from app.schemas.gpu_power import (
    GpuPowerCapabilities,
    GpuPowerConfig,
    GpuPowerState,
    NvidiaStateConfig,
)
from app.services.power.gpu.protocol import GpuPowerBackend

logger = logging.getLogger(__name__)


class NvidiaGpuPowerBackend(GpuPowerBackend):
    def __init__(self) -> None:
        self._detected: bool = False
        self._min_clock: Optional[int] = None
        self._max_clock: Optional[int] = None
        self._min_power: Optional[int] = None
        self._max_power: Optional[int] = None
        self._default_power: Optional[int] = None
        self._detect()

    def _run(self, args: List[str], check: bool = False) -> Optional[subprocess.CompletedProcess]:
        try:
            return subprocess.run(args, capture_output=True, text=True, check=check, timeout=10)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.debug("nvidia-smi run failed: %s", exc)
            return None

    def _detect(self) -> None:
        if shutil.which("nvidia-smi") is None:
            return
        result = self._run(["nvidia-smi", "-L"])
        if result is None or not result.stdout.strip():
            return
        if "GPU 0" not in result.stdout:
            return
        # Query capabilities
        query = self._run([
            "nvidia-smi",
            "--query-gpu=clocks.gr.min,clocks.gr.max,power.min_limit,power.max_limit,power.default_limit",
            "--format=csv,noheader,nounits",
        ])
        if query is not None and query.stdout.strip():
            try:
                parts = [p.strip() for p in query.stdout.strip().splitlines()[0].split(",")]
                if len(parts) == 5:
                    self._min_clock = int(float(parts[0]))
                    self._max_clock = int(float(parts[1]))
                    self._min_power = int(float(parts[2]))
                    self._max_power = int(float(parts[3]))
                    self._default_power = int(float(parts[4]))
            except (ValueError, IndexError) as exc:
                logger.debug("Could not parse nvidia-smi capabilities: %s", exc)

        # Persistence mode (best-effort)
        self._run(["nvidia-smi", "-pm", "1"])
        self._detected = True

    @property
    def detected(self) -> bool:
        return self._detected

    @property
    def vendor(self) -> str:
        return "nvidia"

    async def apply_state(
        self,
        state: GpuPowerState,
        config: Optional[GpuPowerConfig],
    ) -> Tuple[bool, Optional[str]]:
        if not self._detected:
            return False, "NVIDIA GPU not detected"
        if config is None:
            config = GpuPowerConfig()
        state_config = self._effective_state_config(config, state)
        return await asyncio.to_thread(self._apply_sync, state, state_config)

    def _effective_state_config(self, config: GpuPowerConfig, state: GpuPowerState) -> NvidiaStateConfig:
        raw = {
            GpuPowerState.ACTIVE: config.nvidia_active,
            GpuPowerState.STANDBY: config.nvidia_standby,
            GpuPowerState.DEEP_IDLE: config.nvidia_deep_idle,
        }[state]
        # Seed defaults if unset
        if state == GpuPowerState.STANDBY and (raw.min_clock_mhz is None or raw.max_clock_mhz is None):
            mid = (self._min_clock + self._max_clock) // 2 if self._min_clock and self._max_clock else None
            return NvidiaStateConfig(
                min_clock_mhz=raw.min_clock_mhz or self._min_clock,
                max_clock_mhz=raw.max_clock_mhz or mid,
                power_limit_watts=raw.power_limit_watts,
            )
        if state == GpuPowerState.DEEP_IDLE and (raw.min_clock_mhz is None or raw.max_clock_mhz is None):
            return NvidiaStateConfig(
                min_clock_mhz=raw.min_clock_mhz or self._min_clock,
                max_clock_mhz=raw.max_clock_mhz or self._min_clock,
                power_limit_watts=raw.power_limit_watts or self._min_power,
            )
        return raw

    def _apply_sync(self, state: GpuPowerState, sc: NvidiaStateConfig) -> Tuple[bool, Optional[str]]:
        # Active with no overrides → reset
        if state == GpuPowerState.ACTIVE and sc.min_clock_mhz is None and sc.max_clock_mhz is None:
            res = self._run(["nvidia-smi", "-rgc"], check=False)
            if res is None or res.returncode != 0:
                return False, (res.stdout if res else "nvidia-smi -rgc failed")
            if sc.power_limit_watts is None and self._default_power is not None:
                self._run(["nvidia-smi", "-pl", str(self._default_power)])
            return True, None

        # Lock clocks if both bounds given
        if sc.min_clock_mhz is not None and sc.max_clock_mhz is not None:
            res = self._run(
                ["nvidia-smi", "-lgc", f"{sc.min_clock_mhz},{sc.max_clock_mhz}"],
                check=False,
            )
            if res is None or res.returncode != 0:
                return False, (res.stdout if res else "nvidia-smi -lgc failed")

        if sc.power_limit_watts is not None:
            res = self._run(["nvidia-smi", "-pl", str(sc.power_limit_watts)], check=False)
            if res is None or res.returncode != 0:
                return False, (res.stdout if res else "nvidia-smi -pl failed")

        return True, None

    async def current_state(self) -> Optional[GpuPowerState]:
        # NVIDIA doesn't expose state names — best-effort heuristic via current clock cap.
        return None

    async def has_write_permission(self) -> bool:
        # nvidia-smi typically requires either root or nvidia-modprobe SUID
        # for clock/power changes. We don't probe destructively; assume true
        # if we got this far. Real failures surface in apply_state.
        return self._detected

    def capabilities(self) -> GpuPowerCapabilities:
        return GpuPowerCapabilities(
            vendor="nvidia" if self._detected else None,
            nvidia_min_clock_mhz=self._min_clock,
            nvidia_max_clock_mhz=self._max_clock,
            nvidia_min_power_watts=self._min_power,
            nvidia_max_power_watts=self._max_power,
            nvidia_default_power_watts=self._default_power,
        )
