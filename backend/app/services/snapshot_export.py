"""NAS snapshot export for BaluPi companion device.

Collects aggregated NAS metadata into a compact JSON snapshot (~50KB max).
No passwords, tokens, private keys, or IPs are included.
"""
from __future__ import annotations

import logging
import platform
import socket
from datetime import datetime, timezone

import psutil
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app import __version__
from app.core.config import settings

logger = logging.getLogger(__name__)

SNAPSHOT_VERSION = 1


def create_shutdown_snapshot(db: Session) -> dict:
    """Collect NAS metadata for the BaluPi snapshot.

    Args:
        db: Active database session.

    Returns:
        Snapshot dict (JSON-serialisable, ~50KB max).
    """
    return {
        "version": SNAPSHOT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baluhost_version": __version__,
        "system": _collect_system_info(),
        "storage": _collect_storage_info(),
        "smart_health": _collect_smart_health(),
        "services": _collect_services_info(db),
        "users": _collect_users_info(db),
        "files_summary": _collect_files_summary(db),
    }


# ---------------------------------------------------------------------------
# Private collectors
# ---------------------------------------------------------------------------

def _collect_system_info() -> dict:
    """System basics: hostname, uptime, CPU model, RAM."""
    try:
        boot_time = psutil.boot_time()
        uptime = (datetime.now(timezone.utc).timestamp() - boot_time)
    except Exception:
        uptime = 0

    cpu_model: str | None = None
    try:
        from app.services.system import _get_cpu_model
        cpu_model = _get_cpu_model()
    except Exception:
        pass

    mem = psutil.virtual_memory()
    return {
        "hostname": socket.gethostname(),
        "uptime_seconds": int(uptime),
        "cpu_model": cpu_model or platform.processor() or "unknown",
        "ram_total_gb": round(mem.total / (1024 ** 3), 1),
    }


def _collect_storage_info() -> dict:
    """RAID array summary."""
    try:
        from app.services.hardware.raid.api import get_status as raid_get_status
        raid_resp = raid_get_status()
        arrays = []
        total_bytes = 0
        used_bytes = 0
        for arr in raid_resp.arrays:
            arrays.append({
                "name": arr.name,
                "level": arr.level,
                "state": arr.status,
                "size_bytes": arr.size_bytes,
                "devices": [d.name for d in arr.devices],
            })
            total_bytes += arr.size_bytes

        # Get disk usage for the storage path
        try:
            usage = psutil.disk_usage(settings.nas_storage_path)
            used_bytes = usage.used
        except Exception:
            pass

        return {
            "arrays": arrays,
            "total_bytes": total_bytes,
            "used_bytes": used_bytes,
        }
    except Exception as exc:
        logger.debug("Failed to collect storage info: %s", exc)
        return {"arrays": [], "total_bytes": 0, "used_bytes": 0}


def _collect_smart_health() -> dict:
    """SMART health summary per disk."""
    try:
        from app.services.hardware.smart.api import get_smart_status
        smart_resp = get_smart_status()
        result = {}
        for dev in smart_resp.devices:
            result[dev.name] = {
                "status": dev.status,
                "temperature_c": dev.temperature,
                "power_on_hours": dev.last_self_test.power_on_hours if dev.last_self_test else None,
            }
        return result
    except Exception as exc:
        logger.debug("Failed to collect SMART health: %s", exc)
        return {}


def _collect_services_info(db: Session) -> dict:
    """Active VPN clients, shares, last backup."""
    info: dict = {}

    # VPN clients
    try:
        from app.models.vpn import VPNClient
        active_vpn = db.query(func.count(VPNClient.id)).filter(
            VPNClient.is_active == True  # noqa: E712
        ).scalar() or 0
        info["vpn"] = {"active_clients": active_vpn}
    except Exception:
        info["vpn"] = {"active_clients": 0}

    # File shares
    try:
        from app.models.file_share import FileShare
        now = datetime.now(timezone.utc)
        active_shares = db.query(func.count(FileShare.id)).filter(
            or_(
                FileShare.expires_at.is_(None),
                FileShare.expires_at > now,
            )
        ).scalar() or 0
        info["shares"] = {"active_shares": active_shares}
    except Exception:
        info["shares"] = {"active_shares": 0}

    # Last backup
    try:
        from app.models.backup import Backup
        last_backup = (
            db.query(Backup)
            .order_by(Backup.created_at.desc())
            .first()
        )
        if last_backup:
            info["backups"] = {
                "last_backup": last_backup.created_at.isoformat() if last_backup.created_at else None,
                "status": last_backup.status if hasattr(last_backup, "status") else "ok",
            }
        else:
            info["backups"] = {"last_backup": None, "status": "none"}
    except Exception:
        info["backups"] = {"last_backup": None, "status": "unknown"}

    return info


def _collect_users_info(db: Session) -> dict:
    """User summary (no passwords or tokens)."""
    try:
        from app.models.user import User
        users = db.query(User).filter(User.is_active == True).all()  # noqa: E712
        user_list = []
        for u in users:
            user_list.append({
                "username": u.username,
                "role": u.role,
            })
        return {
            "total": len(user_list),
            "list": user_list,
        }
    except Exception as exc:
        logger.debug("Failed to collect user info: %s", exc)
        return {"total": 0, "list": []}


def _collect_files_summary(db: Session) -> dict:
    """File statistics summary."""
    try:
        from app.models.file_metadata import FileMetadata
        total_files = db.query(func.count(FileMetadata.id)).scalar() or 0
        total_size = db.query(func.sum(FileMetadata.size_bytes)).scalar() or 0
        return {
            "total_files": total_files,
            "total_size_bytes": total_size,
        }
    except Exception as exc:
        logger.debug("Failed to collect file summary: %s", exc)
        return {"total_files": 0, "total_size_bytes": 0}
