from __future__ import annotations

import logging
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Protocol

from app.core.config import settings
from app.schemas.system import (
    RaidActionResponse,
    RaidArray,
    RaidDevice,
    RaidOptionsRequest,
    RaidSimulationRequest,
    RaidSpeedLimits,
    RaidStatusResponse,
)

logger = logging.getLogger(__name__)


class RaidBackend(Protocol):
    def get_status(self) -> RaidStatusResponse:
        ...

    def degrade(self, payload: RaidSimulationRequest) -> RaidActionResponse:
        ...

    def rebuild(self, payload: RaidSimulationRequest) -> RaidActionResponse:
        ...

    def finalize(self, payload: RaidSimulationRequest) -> RaidActionResponse:
        ...

    def configure(self, payload: RaidOptionsRequest) -> RaidActionResponse:
        ...


@dataclass
class _RaidState:
    arrays: Dict[str, RaidArray] = field(default_factory=dict)
    speed_limit_min: int = 5000
    speed_limit_max: int = 200000

    @staticmethod
    def _default_size_bytes() -> int:
        quota = settings.nas_quota_bytes
        if quota is not None and quota > 0:
            return quota
        # Fallback to the dev-mode default (10 GiB) when no quota has been configured.
        return 10 * 1024 ** 3

    def ensure_default(self) -> None:
        if self.arrays:
            self.refresh_defaults()
            return

        size_bytes = self._default_size_bytes()
        self.arrays = {
            "md0": RaidArray(
                name="md0",
                level="raid1",
                size_bytes=size_bytes,
                status="optimal",
                devices=[
                    RaidDevice(name="sda1", state="active"),
                    RaidDevice(name="sdb1", state="active"),
                ],
                resync_progress=None,
                bitmap="internal",
                sync_action="idle",
            )
        }

    def refresh_defaults(self) -> None:
        size_bytes = self._default_size_bytes()
        for raid_array in self.arrays.values():
            raid_array.size_bytes = size_bytes

    def configure(self, payload: RaidOptionsRequest) -> None:
        self.ensure_default()
        raid_array = self.arrays.get(payload.array)
        if not raid_array:
            raise KeyError(f"Unknown RAID array '{payload.array}'")

        if payload.enable_bitmap is not None:
            raid_array.bitmap = "internal" if payload.enable_bitmap else None

        if payload.add_spare:
            if any(dev.name == payload.add_spare for dev in raid_array.devices):
                raise ValueError(f"Device '{payload.add_spare}' already part of RAID '{payload.array}'")
            raid_array.devices.append(RaidDevice(name=payload.add_spare, state="spare"))

        if payload.remove_device:
            for idx, dev in enumerate(list(raid_array.devices)):
                if dev.name == payload.remove_device:
                    raid_array.devices.pop(idx)
                    break
            else:
                raise ValueError(f"Device '{payload.remove_device}' not part of RAID '{payload.array}'")

        if payload.write_mostly_device:
            target = None
            for dev in raid_array.devices:
                if dev.name == payload.write_mostly_device:
                    target = dev
                    break
            if target is None:
                raise ValueError(
                    f"Device '{payload.write_mostly_device}' not part of RAID '{payload.array}'"
                )
            if payload.write_mostly is False:
                target.state = "active"
            else:
                target.state = "write-mostly"

        if payload.trigger_scrub:
            raid_array.sync_action = "check"
            raid_array.resync_progress = 0.0
        else:
            if raid_array.sync_action == "check":
                raid_array.sync_action = "idle"
                raid_array.resync_progress = None

        if payload.set_speed_limit_min is not None:
            self.speed_limit_min = max(0, payload.set_speed_limit_min)
        if payload.set_speed_limit_max is not None:
            self.speed_limit_max = max(self.speed_limit_min, payload.set_speed_limit_max)

    def degrade(self, array: str, device: str | None = None) -> None:
        self.ensure_default()
        raid_array = self.arrays.get(array)
        if not raid_array:
            raise KeyError(f"Unknown RAID array '{array}'")

        target_device = device or raid_array.devices[0].name
        for dev in raid_array.devices:
            if dev.name == target_device:
                dev.state = "failed"
                raid_array.status = "degraded"
                raid_array.resync_progress = None
                break
        else:
            raise KeyError(f"Device '{target_device}' not part of RAID '{array}'")

    def rebuild(self, array: str, device: str | None = None) -> None:
        self.ensure_default()
        raid_array = self.arrays.get(array)
        if not raid_array:
            raise KeyError(f"Unknown RAID array '{array}'")

        target_device = device or raid_array.devices[0].name
        for dev in raid_array.devices:
            if dev.name == target_device:
                dev.state = "rebuilding"
                raid_array.status = "rebuilding"
                raid_array.resync_progress = 42.0
                break
        else:
            raise KeyError(f"Device '{target_device}' not part of RAID '{array}'")

    def finalize_rebuild(self, array: str) -> None:
        raid_array = self.arrays.get(array)
        if not raid_array:
            raise KeyError(f"Unknown RAID array '{array}'")

        for dev in raid_array.devices:
            if dev.state in {"failed", "rebuilding"}:
                dev.state = "active"
        raid_array.status = "optimal"
        raid_array.resync_progress = None


@dataclass
class MdstatInfo:
    blocks: Optional[int] = None
    resync_progress: Optional[float] = None


def _parse_mdstat(content: str) -> Dict[str, MdstatInfo]:
    arrays: Dict[str, MdstatInfo] = {}
    current: Optional[str] = None

    for raw_line in content.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        if line.startswith("Personalities") or line.startswith("unused devices"):
            continue

        if not line.startswith(" "):
            parts = line.split()
            if not parts:
                continue
            name = parts[0].rstrip(":")
            arrays[name] = MdstatInfo()
            current = name
            continue

        if current is None:
            continue

        info = arrays[current]
        if info.blocks is None:
            match = re.search(r"(\d+)\s+blocks", line)
            if match:
                info.blocks = int(match.group(1))

        lowered = line.lower()
        if info.resync_progress is None and any(
            keyword in lowered for keyword in ("resync", "recover", "rebuild", "reshape", "check")
        ):
            progress_match = re.search(r"(\d+(?:\.\d+)?)%", line)
            if progress_match:
                try:
                    info.resync_progress = float(progress_match.group(1))
                except ValueError:  # pragma: no cover - defensive conversion
                    info.resync_progress = None

    return arrays


def _extract_detail_value(detail: str, key: str) -> Optional[str]:
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*:\s*(.+)$", re.MULTILINE)
    match = pattern.search(detail)
    if match:
        return match.group(1).strip()
    return None


def _map_device_state(state_text: str) -> str:
    text = state_text.lower()
    if "faulty" in text or "failed" in text:
        return "failed"
    if "remove" in text:
        return "removed"
    if "spare" in text and ("rebuild" in text or "recover" in text):
        return "rebuilding"
    if "rebuild" in text or "recover" in text:
        return "rebuilding"
    if "spare" in text:
        return "spare"
    if "blocked" in text:
        return "blocked"
    if "writemostly" in text:
        return "write-mostly"
    if "sync" in text or "active" in text:
        return "active"
    return text or "unknown"


def _derive_array_status(state_text: Optional[str], progress: Optional[float], devices: List[RaidDevice]) -> str:
    if state_text:
        lowered = state_text.lower()
        if any(keyword in lowered for keyword in ("resync", "recover", "rebuild", "reshape", "check")):
            return "rebuilding"
        if "degraded" in lowered or "faulty" in lowered:
            return "degraded"
        if "inactive" in lowered or "stop" in lowered:
            return "inactive"

    if progress is not None:
        return "rebuilding"

    if any(dev.state in {"failed", "removed"} for dev in devices):
        return "degraded"

    return "optimal"


class DevRaidBackend:
    def __init__(self) -> None:
        self._state = _RaidState()

    def get_status(self) -> RaidStatusResponse:
        self._state.ensure_default()
        return RaidStatusResponse(
            arrays=list(self._state.arrays.values()),
            speed_limits=RaidSpeedLimits(
                minimum=self._state.speed_limit_min,
                maximum=self._state.speed_limit_max,
            ),
        )

    def degrade(self, payload: RaidSimulationRequest) -> RaidActionResponse:
        try:
            self._state.degrade(payload.array, payload.device)
        except KeyError as exc:
            raise ValueError(str(exc)) from exc
        return RaidActionResponse(message=f"Array {payload.array} marked as degraded")

    def rebuild(self, payload: RaidSimulationRequest) -> RaidActionResponse:
        try:
            self._state.rebuild(payload.array, payload.device)
        except KeyError as exc:
            raise ValueError(str(exc)) from exc
        return RaidActionResponse(message=f"Array {payload.array} rebuild started")

    def finalize(self, payload: RaidSimulationRequest) -> RaidActionResponse:
        try:
            self._state.finalize_rebuild(payload.array)
        except KeyError as exc:
            raise ValueError(str(exc)) from exc
        return RaidActionResponse(message=f"Array {payload.array} restored to optimal state")

    def configure(self, payload: RaidOptionsRequest) -> RaidActionResponse:
        try:
            self._state.configure(payload)
        except (KeyError, ValueError) as exc:
            raise ValueError(str(exc)) from exc

        return RaidActionResponse(message="RAID configuration updated (dev mode)")


class MdadmRaidBackend:
    _MDSTAT_PATH = Path("/proc/mdstat")

    def __init__(self) -> None:
        if not self.is_supported():
            raise RuntimeError("mdadm backend is not available on this system")
        self._lsblk_available = shutil.which("lsblk") is not None

    @staticmethod
    def is_supported() -> bool:
        return platform.system().lower() == "linux" and shutil.which("mdadm") is not None

    def get_status(self) -> RaidStatusResponse:
        mdstat_info = self._read_mdstat()
        array_names = set(mdstat_info.keys()) | set(self._scan_arrays())

        if not array_names:
            raise RuntimeError("No RAID arrays managed by mdadm were found")

        arrays: List[RaidArray] = []
        for name in sorted(array_names):
            info = mdstat_info.get(name)
            arrays.append(self._build_array(name, info))

        speed_limits = self._read_speed_limits()

        return RaidStatusResponse(
            arrays=arrays,
            speed_limits=speed_limits,
        )

    def degrade(self, payload: RaidSimulationRequest) -> RaidActionResponse:
        if not payload.device:
            raise ValueError("Device must be provided when failing a RAID member")

        array_path = self._normalize_array(payload.array)
        device_path = self._normalize_device(payload.device)

        self._run(["mdadm", array_path, "--fail", device_path])
        logger.info("Marked device %s as failed in %s", device_path, array_path)
        return RaidActionResponse(message=f"Array {payload.array} marked as degraded (failed {device_path})")

    def rebuild(self, payload: RaidSimulationRequest) -> RaidActionResponse:
        if not payload.device:
            raise ValueError("Device must be provided to start a rebuild")

        array_path = self._normalize_array(payload.array)
        device_path = self._normalize_device(payload.device)

        # Removing the device might fail if it has already been detached; ignore such errors.
        self._run(["mdadm", array_path, "--remove", device_path], check=False)
        self._run(["mdadm", array_path, "--add", device_path])
        logger.info("Rebuild initiated for %s in %s", device_path, array_path)
        return RaidActionResponse(message=f"Array {payload.array} rebuild started for {device_path}")

    def finalize(self, payload: RaidSimulationRequest) -> RaidActionResponse:
        array_path = self._normalize_array(payload.array)
        self._run(["mdadm", "--wait", array_path], timeout=600)

        status = self.get_status()
        array = next((item for item in status.arrays if item.name == payload.array or f"/dev/{item.name}" == payload.array), None)
        if array and array.status != "optimal":
            raise RuntimeError(f"Array {payload.array} is not optimal yet (current status: {array.status})")

        return RaidActionResponse(message=f"Array {payload.array} synchronized and optimal")

    def configure(self, payload: RaidOptionsRequest) -> RaidActionResponse:
        array_path = self._normalize_array(payload.array)
        actions: List[str] = []

        if payload.enable_bitmap is not None:
            option = "internal" if payload.enable_bitmap else "none"
            self._run(["mdadm", array_path, "--grow", f"--bitmap={option}"])
            actions.append(f"bitmap set to {option}")

        if payload.add_spare:
            device_path = self._normalize_device(payload.add_spare)
            self._run(["mdadm", array_path, "--add", device_path])
            actions.append(f"added spare {device_path}")

        if payload.remove_device:
            device_path = self._normalize_device(payload.remove_device)
            self._run(["mdadm", array_path, "--remove", device_path])
            actions.append(f"removed device {device_path}")

        if payload.write_mostly_device:
            device_path = self._normalize_device(payload.write_mostly_device)
            if payload.write_mostly is False:
                self._run(["mdadm", array_path, "--readwrite", device_path])
                actions.append(f"set {device_path} readwrite")
            else:
                self._run(["mdadm", array_path, "--write-mostly", device_path])
                actions.append(f"set {device_path} write-mostly")

        if payload.trigger_scrub:
            self._set_sync_action(payload.array, "check")
            actions.append("triggered scrub")

        if payload.set_speed_limit_min is not None:
            self._write_proc_value(
                Path("/proc/sys/dev/raid/speed_limit_min"),
                str(max(0, payload.set_speed_limit_min)),
            )
            actions.append(f"speed_limit_min={payload.set_speed_limit_min}")

        if payload.set_speed_limit_max is not None:
            max_value = max(
                payload.set_speed_limit_min or 0,
                payload.set_speed_limit_max,
            )
            self._write_proc_value(
                Path("/proc/sys/dev/raid/speed_limit_max"),
                str(max_value),
            )
            actions.append(f"speed_limit_max={max_value}")

        if not actions:
            raise ValueError("No RAID configuration changes supplied")

        return RaidActionResponse(message="; ".join(actions))

    def _build_array(self, name: str, info: Optional[MdstatInfo]) -> RaidArray:
        detail = self._run(["mdadm", f"/dev/{name}", "--detail"]).stdout

        level = _extract_detail_value(detail, "Raid Level") or "unknown"
        state_line = _extract_detail_value(detail, "State")

        size_bytes = self._resolve_array_size(name, info, detail)
        resync_progress = self._resolve_progress(info, detail)
        devices = self._parse_devices(detail)
        status = _derive_array_status(state_line, resync_progress, devices)
        bitmap_info = _extract_detail_value(detail, "Bitmap")
        sync_action = self._read_sync_action(name)

        return RaidArray(
            name=name,
            level=level.lower(),
            size_bytes=size_bytes,
            status=status,
            devices=devices,
            resync_progress=resync_progress,
            bitmap=bitmap_info,
            sync_action=sync_action,
        )

    def _resolve_array_size(self, name: str, info: Optional[MdstatInfo], detail: str) -> int:
        if info and info.blocks is not None:
            return info.blocks * 1024

        # Try to parse the mdadm detail output
        size_text = _extract_detail_value(detail, "Array Size")
        if size_text:
            blocks_match = re.search(r"(\d+)\s+blocks", size_text)
            if blocks_match:
                return int(blocks_match.group(1)) * 1024
            byte_match = re.search(r"(\d+)\s+bytes", size_text)
            if byte_match:
                return int(byte_match.group(1))

        if self._lsblk_available:
            result = self._run(
                [
                    "lsblk",
                    f"/dev/{name}",
                    "--bytes",
                    "--nodeps",
                    "--noheadings",
                    "--output",
                    "SIZE",
                ]
            )
            size_str = result.stdout.strip().splitlines()[0]
            return int(size_str)

        raise RuntimeError(f"Unable to determine size for RAID array '{name}'")

    def _resolve_progress(self, info: Optional[MdstatInfo], detail: str) -> Optional[float]:
        if info and info.resync_progress is not None:
            return info.resync_progress

        for key in ("Resync Status", "Rebuild Status", "Recovery Status", "Check Status"):
            value = _extract_detail_value(detail, key)
            if not value:
                continue
            match = re.search(r"(\d+(?:\.\d+)?)%", value)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:  # pragma: no cover - defensive conversion
                    return None
        return None

    def _parse_devices(self, detail: str) -> List[RaidDevice]:
        devices: List[RaidDevice] = []
        in_table = False

        for raw_line in detail.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("Number"):
                in_table = True
                continue
            if not in_table:
                continue
            if line.startswith("unused devices"):
                break

            parts = line.split()
            if len(parts) < 6:
                continue

            device_path = parts[-1]
            state_tokens = parts[4:-1]
            state_text = " ".join(state_tokens)
            devices.append(RaidDevice(name=Path(device_path).name, state=_map_device_state(state_text)))

        return devices

    def _read_mdstat(self) -> Dict[str, MdstatInfo]:
        if not self._MDSTAT_PATH.exists():
            return {}
        try:
            content = self._MDSTAT_PATH.read_text(encoding="utf-8")
        except OSError as exc:  # pragma: no cover - filesystem edge case
            logger.debug("Failed to read /proc/mdstat: %s", exc)
            return {}
        return _parse_mdstat(content)

    def _read_sync_action(self, name: str) -> Optional[str]:
        path = Path(f"/sys/block/{name}/md/sync_action")
        if not path.exists():
            return None
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            return None

    def _set_sync_action(self, name: str, action: str) -> None:
        path = Path(f"/sys/block/{name}/md/sync_action")
        if not path.exists():
            raise RuntimeError(f"sync_action control not available for array '{name}'")
        try:
            path.write_text(action, encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(f"Failed to set sync_action '{action}' for array '{name}': {exc}") from exc

    def _read_speed_limits(self) -> RaidSpeedLimits:
        min_value = self._read_proc_int(Path("/proc/sys/dev/raid/speed_limit_min"))
        max_value = self._read_proc_int(Path("/proc/sys/dev/raid/speed_limit_max"))
        return RaidSpeedLimits(minimum=min_value, maximum=max_value)

    def _read_proc_int(self, path: Path) -> Optional[int]:
        if not path.exists():
            return None
        try:
            return int(path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None

    def _write_proc_value(self, path: Path, value: str) -> None:
        if not path.exists():
            raise RuntimeError(f"Configuration path '{path}' not available on this system")
        try:
            path.write_text(value, encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(f"Failed to write '{value}' to '{path}': {exc}") from exc

    @staticmethod
    def _scan_arrays() -> List[str]:
        try:
            result = subprocess.run(
                ["mdadm", "--detail", "--scan"],
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as exc:  # pragma: no cover - diagnostic fallback
            logger.debug("mdadm --detail --scan failed: %s", exc.stderr.strip())
            return []

        names: List[str] = []
        for line in result.stdout.splitlines():
            match = re.search(r"ARRAY\s+(/dev/\S+)", line)
            if match:
                names.append(Path(match.group(1)).name)
        return names

    def _normalize_array(self, array: str) -> str:
        path = array if array.startswith("/dev/") else f"/dev/{array}"
        if not Path(path).exists():
            raise ValueError(f"Unknown RAID array '{array}'")
        return path

    def _normalize_device(self, device: str) -> str:
        path = device if device.startswith("/dev/") else f"/dev/{device}"
        if not Path(path).exists():
            raise ValueError(f"Device '{device}' not found on this system")
        return path

    def _run(self, command: List[str], *, check: bool = True, timeout: int = 60) -> subprocess.CompletedProcess[str]:
        logger.debug("Executing command: %s", " ".join(command))
        try:
            return subprocess.run(command, check=check, capture_output=True, text=True, timeout=timeout)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or exc.stdout or "").strip()
            logger.error("Command '%s' failed: %s", " ".join(command), stderr)
            message = stderr or f"Command '{' '.join(command)}' failed with exit code {exc.returncode}"
            raise RuntimeError(message) from exc
        except FileNotFoundError as exc:
            raise RuntimeError(f"Required command not found: {command[0]}") from exc


def _select_backend() -> RaidBackend:
    if settings.is_dev_mode or platform.system().lower() != "linux":
        logger.debug("Using development RAID backend")
        return DevRaidBackend()

    if MdadmRaidBackend.is_supported():
        logger.info("Using mdadm RAID backend")
        return MdadmRaidBackend()

    raise RuntimeError("No supported RAID backend available on this system")


_backend = _select_backend()


def get_status() -> RaidStatusResponse:
    return _backend.get_status()


def simulate_failure(payload: RaidSimulationRequest) -> RaidActionResponse:
    return _backend.degrade(payload)


def simulate_rebuild(payload: RaidSimulationRequest) -> RaidActionResponse:
    return _backend.rebuild(payload)


def finalize_rebuild(payload: RaidSimulationRequest) -> RaidActionResponse:
    return _backend.finalize(payload)


def configure_array(payload: RaidOptionsRequest) -> RaidActionResponse:
    return _backend.configure(payload)
