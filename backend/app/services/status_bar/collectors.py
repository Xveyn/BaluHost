"""Collectors: thin async wrappers over existing services that produce a
partial PillState dict (or None to stay silent). Collectors must not raise."""
import functools
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.services.pihole.service import get_pihole_service  # module-level so tests can patch collectors.get_pihole_service
from app.services.power.sleep import get_sleep_manager  # module-level so tests can patch collectors.get_sleep_manager

logger = logging.getLogger(__name__)


def _safe(default=None):
    """Decorator: swallow any exception in a collector and return `default`."""
    def deco(fn):
        @functools.wraps(fn)
        async def wrapper(db: Session, role: str):
            try:
                return await fn(db, role)
            except Exception as exc:  # noqa: BLE001 - collectors must never 5xx
                logger.debug("collector %s failed: %s", fn.__name__, exc)
                return default
        return wrapper
    return deco


# ── power ────────────────────────────────────────────────────────────
@_safe()
async def collect_power(db: Session, role: str) -> Optional[dict]:
    from app.services.power.manager import get_power_manager
    status = await get_power_manager().get_power_status()
    # PowerStatusResponse exposes the active profile as `current_profile`
    # (a PowerProfile enum). Keep defensive fallbacks for older shapes.
    profile = (
        getattr(status, "current_profile", None)
        or getattr(status, "active_profile", None)
        or getattr(status, "profile", None)
    )
    if not profile:
        return None
    # PowerProfile is a str-enum; its `.value` (e.g. "idle") is the display text.
    raw = getattr(profile, "value", profile)
    label = str(raw).replace("_", " ").title()
    return {"kind": "state", "tone": "info", "label": label, "icon": "Zap"}


# ── pihole ───────────────────────────────────────────────────────────
@_safe()
async def collect_pihole(db: Session, role: str) -> Optional[dict]:
    service = get_pihole_service(db)
    data = await service.get_status()
    if not data.get("connected"):
        return None
    blocking = bool(data.get("blocking_enabled"))
    return {
        "kind": "state",
        "tone": "success" if blocking else "neutral",
        "label": "Pi-hole",
        "value": "on" if blocking else "off",
        "icon": "Shield",
    }


# ── uploads ──────────────────────────────────────────────────────────
@_safe()
async def collect_uploads(db: Session, role: str) -> Optional[dict]:
    from app.services.upload_progress import get_upload_progress_manager
    mgr = get_upload_progress_manager()
    active = [p for p in mgr._progress.values() if getattr(p, "status", None) == "uploading"]
    if not active:
        return None
    return {
        "kind": "activity",
        "tone": "info",
        "label": "Uploads",
        "value": str(len(active)),
        "icon": "Upload",
    }


# ── sync ─────────────────────────────────────────────────────────────
@_safe()
async def collect_sync(db: Session, role: str) -> Optional[dict]:
    from app.models.sync_state import SyncMetadata
    conflicts = (
        db.query(SyncMetadata)
        .filter(SyncMetadata.conflict_detected.is_(True))
        .count()
    )
    if conflicts == 0:
        return None
    return {"kind": "activity", "tone": "warning", "label": "Sync",
            "value": f"{conflicts} conflicts", "icon": "RefreshCw"}


# ── raid ─────────────────────────────────────────────────────────────
def _raid_array_statuses(db: Session) -> list[str]:
    """Return the status string of every RAID array (sync helper for testability)."""
    from app.services.hardware.raid import api as raid_api
    resp = raid_api.get_status()  # RaidStatusResponse | dict
    arrays = getattr(resp, "arrays", None)
    if arrays is None and isinstance(resp, dict):
        arrays = resp.get("arrays")
    arrays = arrays or []
    statuses: list[str] = []
    for a in arrays:
        if isinstance(a, dict):
            statuses.append(a.get("status", "optimal"))
        else:
            statuses.append(getattr(a, "status", "optimal"))
    return statuses


@_safe()
async def collect_raid(db: Session, role: str) -> Optional[dict]:
    statuses = _raid_array_statuses(db)
    bad = [s for s in statuses if s not in ("optimal", "checking")]
    if not bad:
        return None
    failed = any(s in ("inactive",) for s in bad)
    return {
        "kind": "alert",
        "tone": "danger" if failed else "warning",
        "label": "RAID",
        "value": bad[0],
        "icon": "HardDrive",
    }


# ── sleep (schedule status) ──────────────────────────────────────────
@_safe()
async def collect_sleep(db: Session, role: str) -> Optional[dict]:
    manager = get_sleep_manager()
    if manager is None:
        return None
    status = manager.get_status()
    if not getattr(status, "schedule_enabled", False):
        return None
    # `schedule_sleep_time` lives on the config, not the status response —
    # read it from the config (best-effort; value stays None on any miss).
    sleep_time = None
    try:
        config = manager.get_config()
        sleep_time = getattr(config, "schedule_sleep_time", None)
    except Exception:  # noqa: BLE001 - value is optional, never block the pill
        sleep_time = None
    return {"kind": "state", "tone": "neutral", "label": "Sleep",
            "value": sleep_time, "icon": "Moon"}


# ── always-awake (with countdown) ────────────────────────────────────
def _format_countdown(seconds: float) -> str:
    """Format remaining seconds as MM:SS (<1h) or HH:MM:SS (>=1h)."""
    total = max(0, int(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


@_safe()
async def collect_always_awake(db: Session, role: str) -> Optional[dict]:
    manager = get_sleep_manager()
    if manager is None:
        return None
    status = manager.get_status()
    aa = getattr(status, "always_awake", None)
    if aa is None or not aa.enabled:
        return None
    out = {"kind": "state", "tone": "warning", "label": "Always Awake", "icon": "Coffee"}
    if aa.until is None:
        out["value"] = "permanent"
    else:
        secs = aa.expires_in_seconds or 0.0
        out["value"] = _format_countdown(secs)
        out["extra"] = {"expires_in_seconds": secs}
    return out


# ── vpn ──────────────────────────────────────────────────────────────
@_safe()
async def collect_vpn(db: Session, role: str) -> Optional[dict]:
    from app.models.vpn import VPNClient
    count = db.query(VPNClient).count()
    if count == 0:
        return None
    return {"kind": "state", "tone": "success", "label": "VPN",
            "value": str(count), "icon": "Lock"}


# ── scheduler ────────────────────────────────────────────────────────
def _active_executions(db: Session):
    """RUNNING + REQUESTED scheduler executions, newest-started first."""
    from app.models.scheduler_history import SchedulerExecution, SchedulerStatus
    from sqlalchemy import desc
    return (
        db.query(SchedulerExecution)
        .filter(SchedulerExecution.status.in_([
            SchedulerStatus.RUNNING.value, SchedulerStatus.REQUESTED.value,
        ]))
        .order_by(desc(SchedulerExecution.started_at))
        .all()
    )


def _scheduler_display_name(name: str) -> str:
    from app.schemas.scheduler import SCHEDULER_REGISTRY
    info = SCHEDULER_REGISTRY.get(name)
    if info and info.get("display_name"):
        return info["display_name"]
    return name


@_safe()
async def collect_scheduler(db: Session, role: str) -> Optional[dict]:
    rows = _active_executions(db)
    if not rows:
        return None
    jobs = [_scheduler_display_name(r.scheduler_name) for r in rows[:3]]
    return {
        "kind": "activity",
        "tone": "info",
        "label": "Scheduler",
        "value": str(len(rows)),
        "icon": "Clock",
        "extra": {"jobs": jobs},
    }


# ── backup ───────────────────────────────────────────────────────────
def _running_backup(db: Session):
    from app.models.backup import Backup
    return (
        db.query(Backup)
        .filter(Backup.status.in_(["in_progress", "requested"]))
        .order_by(Backup.created_at.desc())
        .first()
    )


def _last_finished_backup(db: Session):
    from app.models.backup import Backup
    return (
        db.query(Backup)
        .filter(Backup.status.in_(["completed", "failed"]))
        .order_by(Backup.created_at.desc())
        .first()
    )


@_safe()
async def collect_backup(db: Session, role: str) -> Optional[dict]:
    from datetime import datetime, timezone, timedelta

    running = _running_backup(db)
    if running is not None:
        return {"kind": "activity", "tone": "info", "label": "Backup",
                "value": "läuft", "icon": "Save"}

    last = _last_finished_backup(db)
    if last is None or last.status != "failed":
        return None

    finished = last.completed_at or last.created_at
    if finished is not None:
        if finished.tzinfo is None:
            finished = finished.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - finished > timedelta(hours=24):
            return None
    return {"kind": "alert", "tone": "danger", "label": "Backup",
            "value": "fehlgeschlagen", "icon": "Save"}


# ── temp / fans ──────────────────────────────────────────────────────
@_safe()
async def collect_temp(db: Session, role: str) -> Optional[dict]:
    from app.services.power.fan_control import get_fan_control_service
    service = get_fan_control_service()
    if service is None:
        return None
    status = await service.get_status()
    hot = []
    for fan in status.get("fans", []):
        # FanControlService.get_status() emits `temperature_celsius` and
        # `emergency_temp_celsius`; keep template field names as fallbacks.
        temp = (
            fan.get("temperature_celsius")
            or fan.get("current_temperature")
            or fan.get("temperature")
        )
        limit = (
            fan.get("emergency_temp_celsius")
            or fan.get("critical_temperature")
            or fan.get("max_temperature")
        )
        if temp is not None and limit is not None and temp >= limit:
            hot.append((fan.get("name", "fan"), temp))
    if not hot:
        return None
    name, temp = hot[0]
    return {"kind": "alert", "tone": "danger", "label": "Temp",
            "value": f"{int(temp)}°C", "icon": "Thermometer"}


# ── registry ─────────────────────────────────────────────────────────
COLLECTORS = {
    "power": collect_power,
    "pihole": collect_pihole,
    "uploads": collect_uploads,
    "sync": collect_sync,
    "raid": collect_raid,
    "sleep": collect_sleep,
    "vpn": collect_vpn,
    "temp": collect_temp,
    "always_awake": collect_always_awake,
    "scheduler": collect_scheduler,
    "backup": collect_backup,
}
