"""
RAID management sub-package.

Re-exports all public and internal symbols for backward compatibility.
All existing imports (``from app.services.hardware.raid import X``) continue
to work unchanged.
"""
from __future__ import annotations

# --- Leaf modules (no internal deps) ---
from app.services.hardware.raid.protocol import RaidBackend
from app.services.hardware.raid.parsing import (
    MdstatInfo,
    _derive_array_status,
    _extract_detail_value,
    _map_device_state,
    _parse_mdstat,
)

# --- Backend implementations ---
from app.services.hardware.raid.dev_backend import DevRaidBackend, _RaidState
from app.services.hardware.raid.mdadm_backend import MdadmRaidBackend

# --- Public API ---
from app.services.hardware.raid.api import (
    _audit_event,
    _backend,
    _payload_to_dict,
    _select_backend,
    add_mock_disk,
    configure_array,
    create_array,
    delete_array,
    find_raid_mountpoint,
    format_disk,
    get_available_disks,
    get_status,
    finalize_rebuild,
    simulate_failure,
    simulate_rebuild,
)

# --- Confirmation system ---
from app.services.hardware.raid.confirmation import (
    execute_confirmation,
    request_confirmation,
)

# --- Scrub scheduler ---
from app.services.hardware.raid.scrub import (
    get_scrub_scheduler_status,
    scrub_now,
    start_scrub_scheduler,
    stop_scrub_scheduler,
)

# Keep a reference to the api module for monkey-patching support
from app.services.hardware.raid import api as _api_module

# Re-export settings so tests that read ``raid.settings`` get the same object
from app.core.config import settings


def __getattr__(name: str):
    """Support reading ``_backend`` and ``settings`` from the package level.

    Tests that do ``raid._backend`` or ``raid.settings`` after monkey-patching
    will be redirected to the canonical location in ``api.py`` / ``config``.
    """
    if name == "_backend":
        return _api_module._backend
    if name == "settings":
        from app.core.config import settings as _s
        return _s
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Protocol
    "RaidBackend",
    # Parsing
    "MdstatInfo",
    "_parse_mdstat",
    "_extract_detail_value",
    "_map_device_state",
    "_derive_array_status",
    # Backends
    "DevRaidBackend",
    "MdadmRaidBackend",
    "_RaidState",
    # API
    "get_status",
    "simulate_failure",
    "simulate_rebuild",
    "finalize_rebuild",
    "configure_array",
    "get_available_disks",
    "format_disk",
    "create_array",
    "delete_array",
    "add_mock_disk",
    "find_raid_mountpoint",
    "_backend",
    "_select_backend",
    "_payload_to_dict",
    "_audit_event",
    # Confirmation
    "request_confirmation",
    "execute_confirmation",
    # Scrub
    "scrub_now",
    "start_scrub_scheduler",
    "stop_scrub_scheduler",
    "get_scrub_scheduler_status",
    # Config (for test patching)
    "settings",
]
