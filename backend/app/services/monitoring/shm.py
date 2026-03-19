"""
Shared-memory IPC via /dev/shm/baluhost/ (Linux) or %TEMP%/baluhost-shm/ (Windows).

Provides atomic JSON read/write for inter-process communication between
the monitoring_worker process and the main Uvicorn web workers.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

if sys.platform == "win32":
    SHM_DIR = Path(tempfile.gettempdir()) / "baluhost-shm"
else:
    SHM_DIR = Path("/dev/shm/baluhost")

# SHM file names
TELEMETRY_FILE = "telemetry.json"
DISK_IO_FILE = "disk_io.json"
POWER_MONITOR_FILE = "power_monitor.json"
ORCHESTRATOR_STATUS_FILE = "orchestrator_status.json"
HEARTBEAT_FILE = "heartbeat.json"
COMMANDS_FILE = "commands.json"
ORCHESTRATOR_DATA_FILE = "orchestrator_data.json"
SMART_DEVICES_FILE = "smart_devices.json"
SMART_DEVICES_CHANGES_FILE = "smart_devices_changes.json"


def _ensure_dir() -> None:
    """Create the SHM directory if it doesn't exist."""
    SHM_DIR.mkdir(parents=True, exist_ok=True)


def write_shm(filename: str, data: Any) -> None:
    """
    Atomically write JSON data to a SHM file.

    Uses tempfile + os.rename for atomic writes (no partial reads).

    Args:
        filename: File name within SHM_DIR
        data: JSON-serializable data
    """
    _ensure_dir()
    target = SHM_DIR / filename

    try:
        fd, tmp_path = tempfile.mkstemp(dir=str(SHM_DIR), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, default=str)
            os.replace(tmp_path, str(target))
        except BaseException:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as exc:
        logger.debug("SHM write failed for %s: %s", filename, exc)


def read_shm(filename: str, max_age_seconds: float = 30.0) -> Optional[Any]:
    """
    Read JSON data from a SHM file with staleness check.

    Args:
        filename: File name within SHM_DIR
        max_age_seconds: Maximum age in seconds before data is considered stale

    Returns:
        Parsed JSON data, or None if file doesn't exist, is stale, or has errors
    """
    target = SHM_DIR / filename

    try:
        if not target.exists():
            return None

        # Staleness check via mtime
        age = time.time() - target.stat().st_mtime
        if age > max_age_seconds:
            logger.debug("SHM file %s is stale (%.1fs old)", filename, age)
            return None

        with open(target, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.debug("SHM read failed for %s: %s", filename, exc)
        return None


def cleanup_shm() -> None:
    """Remove all SHM files and the directory."""
    try:
        if SHM_DIR.exists():
            for f in SHM_DIR.iterdir():
                try:
                    f.unlink()
                except OSError:
                    pass
            try:
                SHM_DIR.rmdir()
            except OSError:
                pass
            logger.info("SHM directory cleaned up")
    except Exception as exc:
        logger.debug("SHM cleanup failed: %s", exc)


def is_monitoring_worker_alive(max_age: float = 30.0) -> bool:
    """
    Check if the monitoring worker process is alive via heartbeat.

    Args:
        max_age: Maximum heartbeat age in seconds

    Returns:
        True if heartbeat is fresh enough
    """
    data = read_shm(HEARTBEAT_FILE, max_age_seconds=max_age)
    return data is not None and data.get("alive", False)


def read_command() -> Optional[dict]:
    """
    Read and consume a pending command from the commands file.

    Returns:
        Command dict, or None if no command pending.
        Deletes the file after reading to ensure one-time consumption.
    """
    target = SHM_DIR / COMMANDS_FILE
    try:
        if not target.exists():
            return None

        with open(target, "r") as f:
            data = json.load(f)

        # Consume: delete after reading
        target.unlink(missing_ok=True)
        return data
    except (json.JSONDecodeError, OSError):
        return None


def write_command(action: str, **kwargs: Any) -> None:
    """
    Write a command for the monitoring worker to consume.

    Args:
        action: Command action (e.g. "pause_monitoring", "resume_monitoring")
        **kwargs: Additional command parameters
    """
    cmd = {"action": action, "timestamp": time.time(), **kwargs}
    write_shm(COMMANDS_FILE, cmd)
