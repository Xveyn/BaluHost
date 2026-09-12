from __future__ import annotations

import datetime
import json
import logging
import platform
from datetime import timezone
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import ServiceUnavailableError
from app.schemas.system import (
    AvailableDisksResponse,
    CreateArrayRequest,
    DeleteArrayRequest,
    FormatDiskRequest,
    RaidActionResponse,
    RaidOptionsRequest,
    RaidSimulationRequest,
    RaidStatusResponse,
)

from app.services.hardware.raid.dev_backend import DevRaidBackend
from app.services.hardware.raid.mdadm_backend import MdadmRaidBackend
from app.services.hardware.raid.protocol import RaidBackend

logger = logging.getLogger(__name__)


def find_raid_mountpoint(raid_name: str) -> str | None:
    """Find mountpoint of a RAID device by reading /proc/mounts.

    More robust than psutil for software-RAID devices (md*).
    Returns the mountpoint path or None if the device is not mounted.
    """
    try:
        with open("/proc/mounts") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    device, mountpoint = parts[0], parts[1]
                    if raid_name in device and "/md" in device:
                        return mountpoint
    except (FileNotFoundError, PermissionError):
        pass
    return None


class RaidUnavailableError(ServiceUnavailableError):
    """No RAID backend on this host (mdadm missing) -> routes answer 503."""

    public_message = "RAID support is not available on this system"


_backend_cache: RaidBackend | None = None


def _select_backend() -> RaidBackend:
    # Respect explicit override in settings first (useful for tests or CI)
    if getattr(settings, "raid_force_dev_backend", False):
        logger.debug("Using development RAID backend (forced by settings)")
        return DevRaidBackend()

    # Non-Linux hosts cannot use mdadm -> fall back to dev backend
    if platform.system().lower() != "linux":
        logger.debug("Non-Linux host detected; using development RAID backend")
        return DevRaidBackend()

    # If nas_mode explicitly requests dev, use dev backend
    if getattr(settings, "is_dev_mode", False):
        logger.debug("Using development RAID backend (nas_mode=dev)")
        return DevRaidBackend()

    # Otherwise prefer the mdadm backend when available
    if MdadmRaidBackend.is_supported():
        logger.info("Using mdadm RAID backend")
        return MdadmRaidBackend()

    raise RaidUnavailableError()


def _get_backend() -> RaidBackend:
    """Resolve the RAID backend on first use and cache it.

    Deliberately NOT resolved at import time. mdadm is an optional dependency
    (the installer defaults to ENABLE_RAID=false), and a module-level
    ``_backend = _select_backend()`` turned a missing mdadm into an ImportError
    that propagated through app.services.hardware into app.main -- the service
    refused to start at all instead of degrading (#543).
    """
    global _backend_cache
    if _backend_cache is None:
        _backend_cache = _select_backend()
    return _backend_cache


def _payload_to_dict(payload: object) -> object:
    try:
        # Pydantic v2
        return payload.model_dump()  # type: ignore[attr-defined]
    except Exception:
        try:
            return payload.dict()  # type: ignore[attr-defined]
        except Exception:
            return str(payload)


def _audit_event(action: str, payload: object | None = None, dry_run: bool = False) -> None:
    """Append a compact audit record to the configured audit file (best-effort).

    The function never raises; failures are logged only.
    """
    record = {
        "timestamp": datetime.datetime.now(timezone.utc).isoformat() + "Z",
        "action": action,
        "dry_run": bool(dry_run),
        "payload": _payload_to_dict(payload) if payload is not None else None,
    }
    logger.info("RAID audit: %s", json.dumps(record, default=str))
    audit_path = getattr(settings, "raid_audit_log", None)
    if not audit_path:
        return
    try:
        p = Path(audit_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
    except Exception as exc:  # pragma: no cover - best-effort logging
        logger.debug("Failed to write RAID audit record to %s: %s", audit_path, exc)


def get_status() -> RaidStatusResponse:
    """Current RAID status, or an empty one when the host has no RAID support.

    The read path degrades instead of failing: a box without mdadm genuinely
    has no arrays, and dashboards/health already render that state. Mutating
    calls below deliberately do NOT degrade -- they let RaidUnavailableError
    through, which the global handler turns into a 503 (#543).
    """
    try:
        return _get_backend().get_status()
    except RaidUnavailableError:
        logger.warning("RAID status requested but no backend is available; reporting no arrays")
        return RaidStatusResponse(arrays=[])


def simulate_failure(payload: RaidSimulationRequest) -> RaidActionResponse:
    _audit_event("simulate_failure", payload, dry_run=getattr(settings, "raid_dry_run", False))
    if getattr(settings, "raid_dry_run", False) and not isinstance(_get_backend(), DevRaidBackend):
        dev = DevRaidBackend()
        resp = dev.degrade(payload)
        resp.message = "[DRY-RUN] " + resp.message
        return resp
    resp = _get_backend().degrade(payload)
    try:
        from app.services.notifications.events import emit_raid_degraded_sync
        emit_raid_degraded_sync(payload.array, details="Manuell ausgelöst (simulate_failure)")
    except Exception as exc:
        logger.debug("Failed to emit RAID degraded notification: %s", exc)
    return resp


def simulate_rebuild(payload: RaidSimulationRequest) -> RaidActionResponse:
    _audit_event("simulate_rebuild", payload, dry_run=getattr(settings, "raid_dry_run", False))
    if getattr(settings, "raid_dry_run", False) and not isinstance(_get_backend(), DevRaidBackend):
        dev = DevRaidBackend()
        resp = dev.rebuild(payload)
        resp.message = "[DRY-RUN] " + resp.message
        return resp
    return _get_backend().rebuild(payload)


def finalize_rebuild(payload: RaidSimulationRequest) -> RaidActionResponse:
    _audit_event("finalize_rebuild", payload, dry_run=getattr(settings, "raid_dry_run", False))
    if getattr(settings, "raid_dry_run", False) and not isinstance(_get_backend(), DevRaidBackend):
        dev = DevRaidBackend()
        resp = dev.finalize(payload)
        resp.message = "[DRY-RUN] " + resp.message
        return resp
    resp = _get_backend().finalize(payload)
    try:
        from app.services.notifications.events import emit_raid_rebuilt_sync
        emit_raid_rebuilt_sync(payload.array)
    except Exception as exc:
        logger.debug("Failed to emit RAID rebuilt notification: %s", exc)
    return resp


def configure_array(payload: RaidOptionsRequest) -> RaidActionResponse:
    _audit_event("configure_array", payload, dry_run=getattr(settings, "raid_dry_run", False))
    if getattr(settings, "raid_dry_run", False) and not isinstance(_get_backend(), DevRaidBackend):
        dev = DevRaidBackend()
        resp = dev.configure(payload)
        resp.message = "[DRY-RUN] " + resp.message
        return resp
    return _get_backend().configure(payload)


def get_available_disks() -> AvailableDisksResponse:
    return _get_backend().get_available_disks()


def format_disk(payload: FormatDiskRequest) -> RaidActionResponse:
    _audit_event("format_disk", payload, dry_run=getattr(settings, "raid_dry_run", False))
    if getattr(settings, "raid_dry_run", False) and not isinstance(_get_backend(), DevRaidBackend):
        dev = DevRaidBackend()
        resp = dev.format_disk(payload)
        resp.message = "[DRY-RUN] " + resp.message
        return resp
    return _get_backend().format_disk(payload)


def create_array(payload: CreateArrayRequest) -> RaidActionResponse:
    _audit_event("create_array", payload, dry_run=getattr(settings, "raid_dry_run", False))
    if getattr(settings, "raid_dry_run", False) and not isinstance(_get_backend(), DevRaidBackend):
        dev = DevRaidBackend()
        resp = dev.create_array(payload)
        resp.message = "[DRY-RUN] " + resp.message
        return resp
    return _get_backend().create_array(payload)


def delete_array(payload: DeleteArrayRequest) -> RaidActionResponse:
    _audit_event("delete_array", payload, dry_run=getattr(settings, "raid_dry_run", False))
    if getattr(settings, "raid_dry_run", False) and not isinstance(_get_backend(), DevRaidBackend):
        dev = DevRaidBackend()
        resp = dev.delete_array(payload)
        resp.message = "[DRY-RUN] " + resp.message
        return resp
    return _get_backend().delete_array(payload)


def add_mock_disk(letter: str, size_gb: int, name: str, purpose: str) -> RaidActionResponse:
    """Dev-Mode only: Add a mock disk dynamically."""
    if not isinstance(_get_backend(), DevRaidBackend):
        raise RuntimeError("Mock disk management is only available in dev mode")
    return _get_backend().add_mock_disk(letter, size_gb, name, purpose)
