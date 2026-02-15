"""SSD Cache (bcache) management service.

Provides two backends:
- DevSsdCacheBackend: In-memory simulation for development
- BcacheSsdCacheBackend: Real bcache integration via sysfs (Linux production)

Module-level functions select the backend automatically based on settings.
"""

from __future__ import annotations

import json
import logging
import platform
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Protocol

from app.core.config import settings
from app.schemas.ssd_cache import (
    CacheAttachRequest,
    CacheConfigureRequest,
    CacheDetachRequest,
    CacheMode,
    CacheStatus,
    ExternalBitmapRequest,
)
from app.schemas.system import RaidActionResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

class SsdCacheBackend(Protocol):
    def get_all_cache_statuses(self) -> List[CacheStatus]: ...
    def get_cache_status(self, array: str) -> CacheStatus | None: ...
    def attach_cache(self, payload: CacheAttachRequest) -> RaidActionResponse: ...
    def detach_cache(self, payload: CacheDetachRequest) -> RaidActionResponse: ...
    def configure_cache(self, payload: CacheConfigureRequest) -> RaidActionResponse: ...
    def set_external_bitmap(self, payload: ExternalBitmapRequest) -> RaidActionResponse: ...


# ---------------------------------------------------------------------------
# Dev Backend
# ---------------------------------------------------------------------------

@dataclass
class _MockCacheEntry:
    array_name: str
    cache_device: str
    bcache_device: str
    mode: CacheMode
    state: str = "running"
    cache_hits: int = 0
    cache_misses: int = 0
    dirty_data_bytes: int = 0
    cache_size_bytes: int = 120 * 1024**3  # 120 GiB default mock SSD
    cache_used_bytes: int = 0
    sequential_cutoff_bytes: int = 4 * 1024 * 1024


class DevSsdCacheBackend:
    """In-memory SSD cache simulation for development mode."""

    MOCK_SSD_NAME = "nvme1n1"
    MOCK_SSD_PARTITION = "nvme1n1p1"
    MOCK_SSD_MODEL = "BaluHost Dev SSD Cache 120GB"
    MOCK_SSD_SIZE_GB = 120

    def __init__(self) -> None:
        self._caches: Dict[str, _MockCacheEntry] = {}
        self._bcache_counter = 0

    def get_all_cache_statuses(self) -> List[CacheStatus]:
        return [self._entry_to_status(e) for e in self._caches.values()]

    def get_cache_status(self, array: str) -> CacheStatus | None:
        entry = self._caches.get(array)
        if entry is None:
            return None
        return self._entry_to_status(entry)

    def attach_cache(self, payload: CacheAttachRequest) -> RaidActionResponse:
        if payload.array in self._caches:
            raise ValueError(f"Array '{payload.array}' already has an SSD cache attached")

        # Check if cache device is already in use
        for entry in self._caches.values():
            if entry.cache_device == payload.cache_device:
                raise ValueError(f"Cache device '{payload.cache_device}' is already in use by array '{entry.array_name}'")

        bcache_name = f"bcache{self._bcache_counter}"
        self._bcache_counter += 1

        self._caches[payload.array] = _MockCacheEntry(
            array_name=payload.array,
            cache_device=payload.cache_device,
            bcache_device=bcache_name,
            mode=payload.mode,
        )

        logger.info(
            "[DEV MODE] Attached SSD cache %s to array %s (mode: %s)",
            payload.cache_device, payload.array, payload.mode.value,
        )
        return RaidActionResponse(
            message=f"[DEV MODE] SSD cache {payload.cache_device} attached to {payload.array} "
                    f"as {bcache_name} (mode: {payload.mode.value})"
        )

    def detach_cache(self, payload: CacheDetachRequest) -> RaidActionResponse:
        entry = self._caches.get(payload.array)
        if entry is None:
            raise ValueError(f"No SSD cache attached to array '{payload.array}'")

        if entry.dirty_data_bytes > 0 and not payload.force:
            raise ValueError(
                f"Cache for '{payload.array}' has {entry.dirty_data_bytes} bytes of dirty data. "
                "Use force=true or switch to writethrough mode first."
            )

        cache_device = entry.cache_device
        del self._caches[payload.array]

        logger.info("[DEV MODE] Detached SSD cache from array %s", payload.array)
        return RaidActionResponse(
            message=f"[DEV MODE] SSD cache {cache_device} detached from {payload.array}"
        )

    def configure_cache(self, payload: CacheConfigureRequest) -> RaidActionResponse:
        entry = self._caches.get(payload.array)
        if entry is None:
            raise ValueError(f"No SSD cache attached to array '{payload.array}'")

        changes: list[str] = []

        if payload.mode is not None:
            entry.mode = payload.mode
            changes.append(f"mode={payload.mode.value}")

        if payload.sequential_cutoff_bytes is not None:
            entry.sequential_cutoff_bytes = payload.sequential_cutoff_bytes
            changes.append(f"sequential_cutoff={payload.sequential_cutoff_bytes}")

        if not changes:
            raise ValueError("No configuration changes provided")

        logger.info("[DEV MODE] Configured SSD cache for %s: %s", payload.array, ", ".join(changes))
        return RaidActionResponse(
            message=f"[DEV MODE] SSD cache for {payload.array} updated: {', '.join(changes)}"
        )

    def set_external_bitmap(self, payload: ExternalBitmapRequest) -> RaidActionResponse:
        logger.info(
            "[DEV MODE] Set external bitmap for %s on %s",
            payload.array, payload.ssd_partition,
        )
        return RaidActionResponse(
            message=f"[DEV MODE] External bitmap for {payload.array} set on {payload.ssd_partition}"
        )

    def get_cached_arrays(self) -> set[str]:
        """Return set of array names that have an active SSD cache."""
        return set(self._caches.keys())

    def get_cache_devices(self) -> set[str]:
        """Return set of device names currently used as cache devices."""
        return {e.cache_device for e in self._caches.values()}

    # Simulation helpers for tests
    def _simulate_io(self, array: str, hits: int = 100, misses: int = 20) -> None:
        """Simulate I/O activity for hit-rate calculation in dev mode."""
        entry = self._caches.get(array)
        if entry:
            entry.cache_hits += hits
            entry.cache_misses += misses
            entry.cache_used_bytes = min(
                entry.cache_used_bytes + (hits + misses) * 4096,
                entry.cache_size_bytes,
            )

    @staticmethod
    def _entry_to_status(entry: _MockCacheEntry) -> CacheStatus:
        total = entry.cache_hits + entry.cache_misses
        hit_rate = (entry.cache_hits / total * 100) if total > 0 else None

        return CacheStatus(
            array_name=entry.array_name,
            cache_device=entry.cache_device,
            bcache_device=entry.bcache_device,
            mode=entry.mode,
            state=entry.state,
            hit_rate_percent=round(hit_rate, 1) if hit_rate is not None else None,
            dirty_data_bytes=entry.dirty_data_bytes,
            cache_size_bytes=entry.cache_size_bytes,
            cache_used_bytes=entry.cache_used_bytes,
            sequential_cutoff_bytes=entry.sequential_cutoff_bytes,
        )


# ---------------------------------------------------------------------------
# Production Backend (bcache via sysfs)
# ---------------------------------------------------------------------------

class BcacheSsdCacheBackend:
    """Real bcache integration for Linux production systems.

    Uses bcache-tools for initial setup and sysfs for runtime management.
    """

    def __init__(self) -> None:
        if not self.is_supported():
            raise RuntimeError("bcache backend requires Linux with bcache-tools installed")
        self._lsblk_available = shutil.which("lsblk") is not None

    @staticmethod
    def is_supported() -> bool:
        return (
            platform.system().lower() == "linux"
            and shutil.which("make-bcache") is not None
        )

    # -- Status --

    def get_all_cache_statuses(self) -> List[CacheStatus]:
        statuses: List[CacheStatus] = []
        bcache_dir = Path("/sys/block")
        for entry in sorted(bcache_dir.iterdir()):
            if entry.name.startswith("bcache"):
                status = self._read_bcache_status(entry.name)
                if status:
                    statuses.append(status)
        return statuses

    def get_cache_status(self, array: str) -> CacheStatus | None:
        for status in self.get_all_cache_statuses():
            if status.array_name == array:
                return status
        return None

    # -- Attach --

    def attach_cache(self, payload: CacheAttachRequest) -> RaidActionResponse:
        cache_dev = self._normalize_device(payload.cache_device)
        array_dev = f"/dev/{payload.array}"

        # Safety: validate SSD (not rotational)
        if self._is_rotational(payload.cache_device):
            raise ValueError(f"Device '{payload.cache_device}' is a rotational disk (HDD), not an SSD")

        # Safety: not OS disk
        if self._is_os_device(payload.cache_device):
            raise ValueError(f"Device '{payload.cache_device}' is part of the OS disk")

        # Create cache set on SSD
        self._run(["make-bcache", "-C", cache_dev])
        logger.info("Created bcache cache set on %s", cache_dev)

        # Register backing device (RAID array)
        self._run(["make-bcache", "-B", array_dev, "--attach", cache_dev])
        logger.info("Attached %s as backing device to cache on %s", array_dev, cache_dev)

        # Find the newly created bcache device and set mode
        bcache_dev = self._find_bcache_for_array(payload.array)
        if bcache_dev:
            self._write_sysfs(f"/sys/block/{bcache_dev}/bcache/cache_mode", payload.mode.value)

        return RaidActionResponse(
            message=f"SSD cache {payload.cache_device} attached to {payload.array} "
                    f"(mode: {payload.mode.value})"
        )

    # -- Detach --

    def detach_cache(self, payload: CacheDetachRequest) -> RaidActionResponse:
        bcache_dev = self._find_bcache_for_array(payload.array)
        if not bcache_dev:
            raise ValueError(f"No bcache device found for array '{payload.array}'")

        bcache_path = Path(f"/sys/block/{bcache_dev}/bcache")

        # Check dirty data
        dirty = self._read_sysfs_int(bcache_path / "dirty_data")
        if dirty and dirty > 0 and not payload.force:
            # Switch to writethrough and wait for flush
            self._write_sysfs(str(bcache_path / "cache_mode"), "writethrough")
            raise ValueError(
                f"Cache has {dirty} bytes of dirty data. Switched to writethrough mode. "
                "Wait for flush to complete, then retry, or use force=true."
            )

        # Detach
        self._write_sysfs(str(bcache_path / "detach"), "1")
        logger.info("Detached bcache %s from array %s", bcache_dev, payload.array)

        # Unregister cache set
        cache_set_uuid = self._read_sysfs(str(bcache_path / "cache" / "set_uuid"))
        if cache_set_uuid:
            unregister_path = f"/sys/fs/bcache/{cache_set_uuid.strip()}/unregister"
            self._write_sysfs(unregister_path, "1")

        return RaidActionResponse(
            message=f"SSD cache detached from {payload.array}"
        )

    # -- Configure --

    def configure_cache(self, payload: CacheConfigureRequest) -> RaidActionResponse:
        bcache_dev = self._find_bcache_for_array(payload.array)
        if not bcache_dev:
            raise ValueError(f"No bcache device found for array '{payload.array}'")

        bcache_path = Path(f"/sys/block/{bcache_dev}/bcache")
        changes: list[str] = []

        if payload.mode is not None:
            self._write_sysfs(str(bcache_path / "cache_mode"), payload.mode.value)
            changes.append(f"mode={payload.mode.value}")

        if payload.sequential_cutoff_bytes is not None:
            self._write_sysfs(
                str(bcache_path / "sequential_cutoff"),
                str(payload.sequential_cutoff_bytes),
            )
            changes.append(f"sequential_cutoff={payload.sequential_cutoff_bytes}")

        if not changes:
            raise ValueError("No configuration changes provided")

        return RaidActionResponse(
            message=f"SSD cache for {payload.array} updated: {', '.join(changes)}"
        )

    # -- External Bitmap --

    def set_external_bitmap(self, payload: ExternalBitmapRequest) -> RaidActionResponse:
        ssd_dev = self._normalize_device(payload.ssd_partition)
        array_dev = f"/dev/{payload.array}"

        if self._is_os_device(payload.ssd_partition):
            raise ValueError(f"Device '{payload.ssd_partition}' is part of the OS disk")

        self._run(["mdadm", array_dev, "--grow", f"--bitmap={ssd_dev}"])

        return RaidActionResponse(
            message=f"External bitmap for {payload.array} set on {payload.ssd_partition}"
        )

    # -- Internal helpers --

    def _read_bcache_status(self, bcache_name: str) -> CacheStatus | None:
        """Read bcache status from sysfs for a given bcache device."""
        bcache_path = Path(f"/sys/block/{bcache_name}/bcache")
        if not bcache_path.exists():
            return None

        mode_str = self._read_sysfs(str(bcache_path / "cache_mode")) or "none"
        # cache_mode sysfs often shows format like "[writethrough] writeback writearound none"
        # Extract the active mode (in brackets)
        if "[" in mode_str:
            mode_str = mode_str.split("[")[1].split("]")[0]
        mode_str = mode_str.strip()

        try:
            mode = CacheMode(mode_str)
        except ValueError:
            mode = CacheMode.NONE

        state = self._read_sysfs(str(bcache_path / "state")) or "unknown"

        # Hit rate
        hits = self._read_sysfs_int(bcache_path / "stats_total" / "cache_hits") or 0
        misses = self._read_sysfs_int(bcache_path / "stats_total" / "cache_misses") or 0
        total = hits + misses
        hit_rate = round(hits / total * 100, 1) if total > 0 else None

        dirty = self._read_sysfs_int(bcache_path / "dirty_data") or 0
        cutoff = self._read_sysfs_int(bcache_path / "sequential_cutoff") or 4 * 1024 * 1024

        # Determine array name from backing device
        array_name = self._find_array_for_bcache(bcache_name) or bcache_name
        cache_device = self._find_cache_device_for_bcache(bcache_name) or "unknown"

        return CacheStatus(
            array_name=array_name,
            cache_device=cache_device,
            bcache_device=bcache_name,
            mode=mode,
            state=state.strip(),
            hit_rate_percent=hit_rate,
            dirty_data_bytes=dirty,
            cache_size_bytes=0,  # Could be read from cache set
            cache_used_bytes=0,
            sequential_cutoff_bytes=cutoff,
        )

    def _find_bcache_for_array(self, array_name: str) -> str | None:
        """Find the bcache device associated with a RAID array."""
        for entry in Path("/sys/block").iterdir():
            if not entry.name.startswith("bcache"):
                continue
            backing_dev = self._read_sysfs(str(entry / "bcache" / "backing_dev_name"))
            if backing_dev and backing_dev.strip() == array_name:
                return entry.name
        return None

    def _find_array_for_bcache(self, bcache_name: str) -> str | None:
        backing = self._read_sysfs(f"/sys/block/{bcache_name}/bcache/backing_dev_name")
        return backing.strip() if backing else None

    def _find_cache_device_for_bcache(self, bcache_name: str) -> str | None:
        cache_path = Path(f"/sys/block/{bcache_name}/bcache/cache")
        if cache_path.exists() and cache_path.is_symlink():
            resolved = cache_path.resolve()
            return resolved.name
        return None

    def _is_rotational(self, device: str) -> bool:
        """Check if device is rotational (HDD) via sysfs."""
        base = device.rstrip("0123456789")  # Strip partition number
        rota_path = Path(f"/sys/block/{base}/queue/rotational")
        if rota_path.exists():
            try:
                return rota_path.read_text().strip() == "1"
            except OSError:
                pass
        return False  # Default to non-rotational if unknown

    def _is_os_device(self, device: str) -> bool:
        """Check if device is part of the OS disk."""
        try:
            result = self._run(["lsblk", "-J", "-o", "NAME,TYPE,MOUNTPOINT", f"/dev/{device}"], check=False)
            if result.returncode != 0:
                return False
            data = json.loads(result.stdout)
            for dev in data.get("blockdevices", []):
                if self._has_root_mount(dev):
                    return True
        except Exception:
            pass
        return False

    @staticmethod
    def _has_root_mount(node: dict) -> bool:
        if node.get("mountpoint") == "/":
            return True
        for child in node.get("children", []):
            if BcacheSsdCacheBackend._has_root_mount(child):
                return True
        return False

    def _normalize_device(self, device: str) -> str:
        return device if device.startswith("/dev/") else f"/dev/{device}"

    @staticmethod
    def _read_sysfs(path: str) -> str | None:
        try:
            return Path(path).read_text(encoding="utf-8").strip()
        except (OSError, FileNotFoundError):
            return None

    @staticmethod
    def _read_sysfs_int(path: Path | str) -> int | None:
        try:
            text = Path(path).read_text(encoding="utf-8").strip()
            return int(text)
        except (OSError, FileNotFoundError, ValueError):
            return None

    @staticmethod
    def _write_sysfs(path: str, value: str) -> None:
        try:
            Path(path).write_text(value, encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(f"Failed to write '{value}' to sysfs path '{path}': {exc}") from exc

    def _run(
        self,
        command: List[str],
        *,
        check: bool = True,
        timeout: int = 60,
    ) -> subprocess.CompletedProcess[str]:
        logger.debug("Executing: %s", " ".join(command))
        try:
            return subprocess.run(
                command, check=check, capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or exc.stdout or "").strip()
            logger.error("Command '%s' failed: %s", " ".join(command), stderr)
            raise RuntimeError(stderr or f"Command failed with exit code {exc.returncode}") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Command timed out after {timeout}s") from exc
        except FileNotFoundError as exc:
            raise RuntimeError(f"Required command not found: {command[0]}") from exc


# ---------------------------------------------------------------------------
# Backend selection & module-level API
# ---------------------------------------------------------------------------

def _select_backend() -> SsdCacheBackend:
    if not getattr(settings, "ssd_cache_enabled", True):
        logger.debug("SSD cache disabled; using dev backend as stub")
        return DevSsdCacheBackend()

    if getattr(settings, "ssd_cache_force_dev_backend", False):
        logger.debug("Using development SSD cache backend (forced by settings)")
        return DevSsdCacheBackend()

    if platform.system().lower() != "linux":
        logger.debug("Non-Linux host; using development SSD cache backend")
        return DevSsdCacheBackend()

    if getattr(settings, "is_dev_mode", False):
        logger.debug("Using development SSD cache backend (nas_mode=dev)")
        return DevSsdCacheBackend()

    if BcacheSsdCacheBackend.is_supported():
        logger.info("Using bcache SSD cache backend")
        return BcacheSsdCacheBackend()

    logger.info("bcache-tools not available; SSD cache features disabled")
    return DevSsdCacheBackend()


_backend = _select_backend()


def _payload_to_dict(payload: object) -> object:
    try:
        return payload.model_dump()  # type: ignore[attr-defined]
    except Exception:
        try:
            return payload.dict()  # type: ignore[attr-defined]
        except Exception:
            return str(payload)


def _audit_event(action: str, payload: object | None = None) -> None:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "action": action,
        "payload": _payload_to_dict(payload) if payload is not None else None,
    }
    logger.info("SSD cache audit: %s", json.dumps(record, default=str))


# -- Public module functions --

def get_all_cache_statuses() -> List[CacheStatus]:
    return _backend.get_all_cache_statuses()


def get_cache_status(array: str) -> CacheStatus | None:
    return _backend.get_cache_status(array)


def attach_cache(payload: CacheAttachRequest) -> RaidActionResponse:
    _audit_event("attach_cache", payload)
    return _backend.attach_cache(payload)


def detach_cache(payload: CacheDetachRequest) -> RaidActionResponse:
    _audit_event("detach_cache", payload)
    return _backend.detach_cache(payload)


def configure_cache(payload: CacheConfigureRequest) -> RaidActionResponse:
    _audit_event("configure_cache", payload)
    return _backend.configure_cache(payload)


def set_external_bitmap(payload: ExternalBitmapRequest) -> RaidActionResponse:
    _audit_event("set_external_bitmap", payload)
    return _backend.set_external_bitmap(payload)


def get_cache_devices() -> set[str]:
    """Return device names currently used as cache devices (for disk filtering)."""
    if isinstance(_backend, DevSsdCacheBackend):
        return _backend.get_cache_devices()
    # For production, derive from statuses
    return {s.cache_device for s in _backend.get_all_cache_statuses()}


def get_cached_arrays() -> set[str]:
    """Return array names that have an active SSD cache."""
    if isinstance(_backend, DevSsdCacheBackend):
        return _backend.get_cached_arrays()
    return {s.array_name for s in _backend.get_all_cache_statuses()}


# Two-step confirmation for attach/detach
_confirmations: Dict[str, Dict] = {}


def request_cache_confirmation(action: str, payload: object, ttl_seconds: int = 3600) -> dict:
    """Create a one-time confirmation token for a cache operation."""
    token = uuid.uuid4().hex
    expires_at = int(time.time()) + ttl_seconds
    _confirmations[token] = {
        "action": action,
        "payload": _payload_to_dict(payload),
        "expires_at": expires_at,
    }
    _audit_event("request_cache_confirmation", {"action": action, "token": token})
    return {"token": token, "expires_at": expires_at}


def execute_cache_confirmation(token: str) -> RaidActionResponse:
    """Execute a previously requested cache confirmation token."""
    entry = _confirmations.get(token)
    if not entry:
        raise KeyError("Invalid confirmation token")
    if int(time.time()) > int(entry.get("expires_at", 0)):
        del _confirmations[token]
        raise KeyError("Confirmation token expired")

    action = entry["action"]
    payload = entry["payload"]
    del _confirmations[token]

    if action == "attach_cache":
        return attach_cache(CacheAttachRequest(**payload))
    elif action == "detach_cache":
        return detach_cache(CacheDetachRequest(**payload))
    else:
        raise RuntimeError(f"Unsupported confirmed cache action: {action}")
